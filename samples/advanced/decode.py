# This copyright notice applies to this file only
#
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

'''
This sample demonstrates basic video decoding using the native decoder in PyNvVideoCodec.

It shows how to:
1. Create and use a demuxer to extract packets from a video file
2. Set up a basic decoder for hardware-accelerated decoding
3. Process packets and decode frames
4. Write raw decoded frames to a file

Key Learning Outcomes:
1. Basic demuxer usage for extracting video packets
2. Setting up hardware decoder with default configuration
3. Understanding the decode pipeline: Video File -> Demuxer -> Packets -> Decoder -> Raw Frames
4. Working with both device and host memory for frame data
5. Managing frame count and early termination


Usage: python decode.py -i <input_video_file> -o <output_file> -d <use_device_memory>
Example: python decode.py -i input.mp4 -o output.yuv -d 1

Arguments:
  -i: Input video file
  -o: Output raw video file (default: <input_name>.yuv)
  -d: Use device memory (1) or host memory (0) (default: 1)
  -g: GPU ID to use (default: 0)
  -f: Number of frames to decode (optional, default: all frames)
'''

import sys
from pathlib import Path
import PyNvVideoCodec as nvc
from os.path import join, dirname, abspath, splitext
# Add the parent directory to Python path in a way that works from any working directory
current_dir = dirname(abspath(__file__))
parent_dir = dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Import utilities for decoding
from utils.decode_parser import parse_decode_args
from utils.Utils import get_frame_data



def decode(gpu_id, enc_file_path, dec_file_path, use_device_memory, frame_count=None):
    """
    Function to decode media file and write raw frames into an output file.

    This function demonstrates basic hardware-accelerated video decoding. Here's how it works:
    1. Creates a demuxer that reads the video file and extracts encoded frame packets
    2. Sets up a GPU decoder with default configuration
    3. The demuxer automatically extracts frame packets as you iterate over it
    4. Each packet is sent to the GPU decoder for hardware-accelerated decoding
    5. The decoder outputs raw YUV frames that can be processed or saved

    Parameters:
        gpu_id (int): Ordinal of GPU to use
        enc_file_path (str): Path to file to be decoded
        dec_file_path (str): Path to output file into which raw frames are stored
        use_device_memory (int): If set to 1, output decoded frame is device pointer wrapped in backend array interface
        frame_count (int, optional): Maximum number of frames to decode. If None, 0, or negative, decode all frames.

            Example:
            >>> decode(0, "path/to/input/media/file","path/to/output/yuv", 1)
            Function to decode media file and write raw frames into an output file.
    """
    # Normalize frame count
    decode_all = frame_count is None or frame_count <= 0
    if decode_all:
        print("Decoding all available frames")
        frame_count = None

    try:
        nv_dmx = nvc.CreateDemuxer(filename=enc_file_path)

        caps = nvc.GetDecoderCaps(
            gpuid=gpu_id,
            codec=nv_dmx.GetNvCodecId(),
            chromaformat=nv_dmx.ChromaFormat(),
            bitdepth=nv_dmx.BitDepth()
        )
        if "num_decoder_engines" in caps:
            print("Number of NVDECs:", caps["num_decoder_engines"])

        nv_dec = nvc.CreateDecoder(gpuid=gpu_id,
                               codec=nv_dmx.GetNvCodecId(),
                               usedevicememory=use_device_memory)

        # printing out FPS and pixel format of the stream for convenience
        print("FPS =", nv_dmx.FrameRate())
        # open the file to be decoded in write mode
        with open(dec_file_path, "wb") as decFile:
            # demuxer can be iterated, fetch the packet from demuxer
            frames_decoded = 0
            for packet in nv_dmx:
                # Decode returns a list of packets, range of this list is from [0, size of (decode picture buffer)]
                # size of (decode picture buffer) depends on GPU, fur Turing series its 8
                for decoded_frame in nv_dec.Decode(packet):
                    frame_data = get_frame_data(decoded_frame, use_device_memory)
                    decFile.write(bytearray(frame_data))

                    frames_decoded += 1
                    if frame_count is not None and frames_decoded >= frame_count:
                        print(f"Successfully decoded requested {frame_count} frames to {dec_file_path}")
                        return

            # If we get here, we've decoded all available frames
            if frame_count is not None and frames_decoded < frame_count:
                print(f"Warning: Video ended before reaching requested frame count. Requested: {frame_count}, Decoded: {frames_decoded}")
                print(f"Decoded frames written to {dec_file_path}")
            else:
                print(f"Successfully decoded all {frames_decoded} frames to {dec_file_path}")

    except nvc.PyNvVCExceptionUnsupported as e:
        print(f"Operation or configuration not supported: {e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise
    finally:
        # Cleanup resources in reverse order of creation
        if nv_dec is not None:
            del nv_dec
        if nv_dmx is not None:
            del nv_dmx

if __name__ == "__main__":
    args = parse_decode_args(
        "Basic video demuxing and decoding example. "
        "Shows how to extract packets from a video file and decode them using the NVIDIA decoder."
    )
    print("=" * 60)
    print("Configuration:")
    print(f"Input: {args.encoded_file_path}")
    print(f"Output: {args.raw_file_path}")
    print(f"GPU ID: {args.gpu_id}")
    print(f"Use Device Memory: {args.use_device_memory}")
    print(f"Frame Count: {args.frame_count if args.frame_count else 'All frames'}")
    print("=" * 60)

    decode(
        gpu_id=args.gpu_id,
        enc_file_path=args.encoded_file_path,
        dec_file_path=args.raw_file_path,
        use_device_memory=args.use_device_memory,
        frame_count=args.frame_count
    )