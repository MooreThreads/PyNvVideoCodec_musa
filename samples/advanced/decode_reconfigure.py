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
This sample demonstrates dynamic decoder reconfiguration for handling resolution changes.
It shows how to:
1. Create a decoder that can handle multiple resolutions
2. Switch between input streams with different dimensions
3. Reconfigure decoder parameters on the fly
4. Handle decoder state during reconfiguration


Usage: python decode_reconfigure.py -i1 <input1> -i2 <input2> -o1 <output1> -o2 <output2>
Example: python decode_reconfigure.py -i1 video1.mp4 -i2 video2.mp4

Arguments:
  -i1: First input video file
  -i2: Second input video file (different resolution)
  -o1: First output raw video file (default: <input1_name>.yuv)
  -o2: Second output raw video file (default: <input2_name>.yuv)
  -d: Use device memory (1) or host memory (0) (default: 1)
  -g: GPU ID to use (default: 0)
  -f: Number of frames to decode per stream (optional)
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

from utils.decode_parser import parse_reconfigure_args
from utils.Utils import get_frame_data

def decode_stream(nv_dec, demuxer, output_file, use_device_memory, frame_count=None):
    """
    Helper function to decode a single stream and write frames to output file.

    Parameters:
        nv_dec: NvDecoder instance
        demuxer: Demuxer instance for the input stream
        output_file: File object to write decoded frames to
        use_device_memory (int): If set to 1, output decoded frame is device pointer wrapped in backend array interface
        frame_count (int, optional): Maximum number of frames to decode. If None, 0, or negative, decode all frames.

    Returns:
        int: Number of frames decoded
    """
    frames_decoded = 0
    for packet in demuxer:
        for decoded_frame in nv_dec.Decode(packet):
            frame_data = get_frame_data(decoded_frame, use_device_memory)
            output_file.write(bytearray(frame_data))
            frames_decoded += 1
            if frame_count is not None and frame_count > 0 and frames_decoded >= frame_count:
                break
        if frame_count is not None and frame_count > 0 and frames_decoded >= frame_count:
            break
    return frames_decoded

def decode_with_reconfigure(gpu_id, enc_file_path1, enc_file_path2, dec_file_path1, dec_file_path2, use_device_memory, frame_count=None):
    """
    Function to decode media files with dynamic decoder reconfiguration.
    Demonstrates switching between two different input streams with different dimensions.

    Parameters:
        gpu_id (int): Ordinal of GPU to use
        enc_file_path1 (str): Path to first input encoded file
        enc_file_path2 (str): Path to second input encoded file with different dimensions
        dec_file_path1 (str): Path to first output file into which raw frames are stored
        dec_file_path2 (str): Path to second output file into which raw frames are stored
        use_device_memory (int): If set to 1, output decoded frame is device pointer wrapped in backend array interface
        frame_count (int, optional): Maximum number of frames to decode per stream. If None, 0, or negative, decode all frames.
    """
    try:
        # Create first demuxer and get stream info
        nv_dmx1 = nvc.CreateDemuxer(filename=enc_file_path1)
        stream1_codec = nv_dmx1.GetNvCodecId()
        stream1_width = nv_dmx1.Width()
        stream1_height = nv_dmx1.Height()
        print(f"\nStream 1 info:")
        print(f"Dimensions: {stream1_width}x{stream1_height}")
        print(f"Codec: {stream1_codec}")
        print(f"FPS: {nv_dmx1.FrameRate()}")

        # Create second demuxer and get stream info
        nv_dmx2 = nvc.CreateDemuxer(filename=enc_file_path2)
        stream2_codec = nv_dmx2.GetNvCodecId()
        stream2_width = nv_dmx2.Width()
        stream2_height = nv_dmx2.Height()
        print(f"\nStream 2 info:")
        print(f"Dimensions: {stream2_width}x{stream2_height}")
        print(f"Codec: {stream2_codec}")
        print(f"FPS: {nv_dmx2.FrameRate()}\n")

        # Create decoder
        nv_dec = nvc.CreateDecoder(
            gpuid=gpu_id,
            codec=stream1_codec,
            usedevicememory=use_device_memory,
            maxwidth=max(stream1_width, stream2_width),
            maxheight=max(stream1_height, stream2_height)
        )

        # Open output files for writing decoded frames
        with open(dec_file_path1, "wb") as decFile1, open(dec_file_path2, "wb") as decFile2:
            # First decode stream 1
            print("Decoding stream 1...")
            frames_decoded = decode_stream(nv_dec, nv_dmx1, decFile1, use_device_memory, frame_count)
            print(f"\nCompleted stream 1: {frames_decoded} frames decoded")
            if frames_decoded > 0:
                print(f"Decoded frames written to {dec_file_path1}\n")
            else:
                print("No frames were decoded from stream 1\n")
            print("Reconfiguring decoder for stream 2...")

            # Reconfigure decoder for stream 2
            nv_dec.setReconfigParams(stream2_width, stream2_height)
            print(f"Decoder reconfigured to dimensions: {stream2_width}x{stream2_height}\n")

            # Now decode stream 2
            print("Decoding stream 2...")
            frames_decoded = decode_stream(nv_dec, nv_dmx2, decFile2, use_device_memory, frame_count)
            print(f"\nCompleted stream 2: {frames_decoded} frames decoded")
            if frames_decoded > 0:
                print(f"Decoded frames written to {dec_file_path2}")
            else:
                print("No frames were decoded from stream 2")

    except nvc.PyNvVCExceptionUnsupported as e:
        print(f"CreateDecoder failure: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    args = parse_reconfigure_args(
        "This sample application demonstrates decoder reconfiguration between two input streams with different dimensions."
    )

    print("=" * 60)
    print("Configuration:")
    print(f"Input 1: {args.input_file1}")
    print(f"Input 2: {args.input_file2}")
    print(f"Output 1: {args.raw_file_path1}")
    print(f"Output 2: {args.raw_file_path2}")
    print(f"GPU ID: {args.gpu_id}")
    print(f"Use Device Memory: {args.use_device_memory}")
    print(f"Frame Count: {args.frame_count if args.frame_count else 'All frames'}")
    print("=" * 60)

    decode_with_reconfigure(
        args.gpu_id,
        args.input_file1,
        args.input_file2,
        args.raw_file_path1,
        args.raw_file_path2,
        args.use_device_memory,
        args.frame_count
    )
