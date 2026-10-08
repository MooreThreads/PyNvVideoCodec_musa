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
This sample demonstrates low-latency video decoding using the native decoder.
It shows how to:
1. Configure different decoder latency modes
2. Use zero-latency decoding for minimal delay
3. Control frame output ordering
4. Set end-of-picture flags for immediate decode


The DisplayDecodeLatencyType enumeration defines three possible latency modes:

- NATIVE: For a stream with B-frames, there is at least 1 frame latency between submitting an input packet and
          getting the decoded frame in display order.

- LOW: For All-Intra and IPPP sequences (without B-frames), there is no latency between submitting an input packet
       and getting the decoded frame in display order. Do not use this flag if the stream contains B-frames.
       This mode maintains proper display ordering.

- ZERO: Enables zero latency for All-Intra / IPPP streams. Do not use this flag if the stream contains B-frames.
        This mode maintains decode ordering.


Usage: python decode_with_low_latency.py -i <input_video_file> -o <output_file> -dl <latency_mode>
Example: python decode_with_low_latency.py -i input.mp4 -o output.yuv -dl 1

Arguments:
  -i: Input video file
  -o: Output raw video file (default: <input_name>.yuv)
  -d: Use device memory (1) or host memory (0) (default: 1)
  -g: GPU ID to use (default: 0)
  -f: Number of frames to decode (optional, default: all frames)
  -dl: Decode latency mode (0: NATIVE, 1: LOW, 2: ZERO)
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
from utils.decode_parser import parse_low_latency_args
from utils.Utils import get_frame_data



def decode(gpu_id, enc_file_path, dec_file_path, use_device_memory, decode_latency, frame_count=None):
    """
    Function to decode media file and write raw frames into an output file.
    Demonstrates different latency modes for decoding:
    - NATIVE: Default mode with 4 frame latency, output in display order
    - LOW: Zero frame latency, output in display order
    - ZERO: Zero frame latency, output in decode order

    Parameters:
        gpu_id (int): Ordinal of GPU to use
        enc_file_path (str): Path to file to be decoded
        dec_file_path (str): Path to output file into which raw frames are stored
        use_device_memory (int): If set to 1, output decoded frame is device pointer wrapped in backend array interface
        decode_latency (nvc.DisplayDecodeLatencyType): Latency mode for decoding
        frame_count (int, optional): Maximum number of frames to decode. If None, 0, or negative, decode all frames.
    """
    # Validate frame count if provided
    if frame_count is None or frame_count <= 0:
        print(f"Decoding all available frames")
        frame_count = None  # Reset to None to decode all frames

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

        # Create decoder with specified latency mode
        nv_dec = nvc.CreateDecoder(gpuid=gpu_id,
                               codec=nv_dmx.GetNvCodecId(),
                               usedevicememory=use_device_memory,
                               latency=decode_latency)

        # Print latency mode information
        latency_mode = "NATIVE (4 frame latency, display order)"
        if decode_latency == nvc.DisplayDecodeLatencyType.LOW:
            latency_mode = "LOW (0 frame latency, display order)"
        elif decode_latency == nvc.DisplayDecodeLatencyType.ZERO:
            latency_mode = "ZERO (0 frame latency, decode order)"
        print(f"Decoding with latency mode: {latency_mode}")
        print("FPS =", nv_dmx.FrameRate())

        # open the file to be decoded in write mode
        with open(dec_file_path, "wb") as decFile:
            frames_decoded = 0
            for packet in nv_dmx:
                # For low latency modes, set ENDOFPICTURE flag to trigger immediate decode
                if decode_latency in [nvc.DisplayDecodeLatencyType.LOW, nvc.DisplayDecodeLatencyType.ZERO]:
                    packet.decode_flag = nvc.VideoPacketFlag.ENDOFPICTURE

                for decoded_frame in nv_dec.Decode(packet):
                    # Get frame data using Utils helper function
                    frame_data = get_frame_data(decoded_frame, use_device_memory)
                    decFile.write(bytearray(frame_data))

                    frames_decoded += 1
                    if frame_count is not None and frame_count > 0 and frames_decoded >= frame_count:
                        print(f"Reached requested frame count: {frame_count}. Frames written to {dec_file_path}")
                        return

            if frame_count is not None and frame_count > 0 and frames_decoded < frame_count:
                print(f"Video ended before reaching requested frame count. Decoded {frames_decoded} frames")

            if frames_decoded > 0:
                print(f"Decoded {frames_decoded} frames written to {dec_file_path}")
            else:
                print("No frames were decoded")
    except nvc.PyNvVCExceptionUnsupported as e:
        print(f"CreateDecoder failure: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":

    args = parse_low_latency_args()

    # Map latency mode to nvc type
    latency_map = {
        0: nvc.DisplayDecodeLatencyType.NATIVE,
        1: nvc.DisplayDecodeLatencyType.LOW,
        2: nvc.DisplayDecodeLatencyType.ZERO
    }
    decode_latency = latency_map[args.decode_latency]
    latency_names = {0: "NATIVE", 1: "LOW", 2: "ZERO"}

    print("=" * 60)
    print("Configuration:")
    print(f"Input: {args.encoded_file_path}")
    print(f"Output: {args.raw_file_path}")
    print(f"GPU ID: {args.gpu_id}")
    print(f"Use Device Memory: {args.use_device_memory}")
    print(f"Frame Count: {args.frame_count if args.frame_count else 'All frames'}")
    print(f"Decode Latency: {latency_names[args.decode_latency]}")
    print("=" * 60)

    decode(
        gpu_id=args.gpu_id,
        enc_file_path=args.encoded_file_path,
        dec_file_path=args.raw_file_path,
        use_device_memory=args.use_device_memory,
        decode_latency=decode_latency,
        frame_count=args.frame_count
    )