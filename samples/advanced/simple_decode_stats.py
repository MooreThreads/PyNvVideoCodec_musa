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
This sample demonstrates how to extract and analyze decode statistics using SimpleDecoder
in PyNvVideoCodec. It shows how to:
1. Enable statistics collection with SimpleDecoder
2. Extract statistics from decoded frames
3. Parse and analyze the statistics
4. Write formatted results to a file


Core module for handling decode statistics.

This module provides functionality for extracting and analyzing low-level video decoding
statistics from H.264/H.265 streams. The following statistics are collected and analyzed:

1. QP (Quantization Parameter) Analysis:
   - Average, min, max QP values per frame
   - Indicates compression level and quality trade-offs
   - Higher QP = more compression, potentially lower quality

2. CU (Coding Unit) Type Distribution:
   - INTRA: Spatial prediction (current frame only)
   - INTER: Temporal prediction (motion compensation)
   - SKIP: Copy from reference without residual
   - PCM: Uncompressed raw pixel values

3. Motion Vector Statistics:
   - MV0: Primary motion vectors (L0 reference)
   - MV1: Secondary motion vectors (L1 reference, B-frames)
   - Magnitude analysis for temporal complexity assessment

4. Macroblock Details:
   - Per-block encoding decisions and parameters
   - Motion vector coordinates and directions
   - QP values and prediction types for debugging

These statistics are valuable for:
- Video quality analysis
- Encoder behavior understanding
- Performance optimization
- Debugging encoding/decoding issues

Usage: python single_decode_stats.py -i <input_video_file> -p <output_stats_file> -d <use_device_memory>
Example: python single_decode_stats.py -i test_video.mp4 -p test_video_stats.txt -d 0

Arguments:
  -i: Input video file
  -p: Output file for statistics (default: <input_name>_stats.txt)
  -d: Use device memory (1) or host memory (0) (default: 1)
  -g: GPU ID to use (default: 0)

Note: For large videos, consider processing in segments to manage memory usage.
'''

import sys
import argparse
from pathlib import Path
import PyNvVideoCodec as nvc
from os.path import join, dirname, abspath

# Add the parent directory to Python path in a way that works from any working directory
current_dir = dirname(abspath(__file__))
parent_dir = dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Import utilities for decoding
from utils.decode_parser import parse_stats_args
from utils.Utils import get_frame_data
from utils.decode_stats_writer import DecodeStatsWriter


def decode(gpu_id, enc_file_path, stats_file_path, use_device_memory, need_scanned_stream_metadata):
    """
    Function to decode media file, write decode statistics into output file.

    Parameters:
        gpu_id (int): Ordinal of GPU to use
        enc_file_path (str): Path to file to be decoded
        stats_file_path (str): Path to output file for decode statistics
        use_device_memory (int): If set to 1, output decoded frame is device pointer wrapped in backend array interface
        need_scanned_stream_metadata (bool): If True, scan stream for detailed metadata (keyframe locations, etc.)

    Returns:
        None
    """

    with open(stats_file_path, "w", newline='\n') as stats_file:
        try:
            # Initialize decoder
            simple_decoder = nvc.SimpleDecoder(
                enc_file_path,
                need_scanned_stream_metadata=need_scanned_stream_metadata,
                use_device_memory=use_device_memory,
                gpu_id=gpu_id,
                enableDecodeStats=True
            )

            # Get metadata and initialize stats writer
            metadata = simple_decoder.get_stream_metadata()
            stats_writer = DecodeStatsWriter(stats_file)

            stats_count = 0
            decoded_frame_count = 0

            # Process frames
            for decoded_frame in simple_decoder:
                if hasattr(decoded_frame, 'decode_stats_size') and decoded_frame.decode_stats_size > 0:
                    try:
                        parsed_stats = decoded_frame.ParseDecodeStats()
                        if len(parsed_stats.get("qp_luma", [])) > 0:
                            stats_count += 1
                            stats_writer.write_frame_stats(
                                decoded_frame_count,
                                parsed_stats
                            )
                    except Exception as e:
                        print(f"Frame {decoded_frame_count}: API parsing failed: {e}")

                decoded_frame_count += 1

            # Print summary
            print(f"Decoded {decoded_frame_count} frames")
            if stats_count == 0:
                print(f"Decode statistics not found")
            else:
                print(f"Decode statistics of {stats_count} frames written to: {stats_file_path}\n")

        except nvc.PyNvVCExceptionUnsupported as e:
            print(f"CreateDecoder failure: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    args = parse_stats_args(
        "This sample application demonstrates decoding media files and extracting decode statistics. "
        "Use -p to enable parsing and text output."
    )

    print("=" * 60)
    print("Configuration:")
    print(f"Input: {args.encoded_file_path}")
    print(f"Stats Output: {args.stats_file_path}")
    print(f"GPU ID: {args.gpu_id}")
    print(f"Use Device Memory: {args.use_device_memory}")
    print(f"Need Scanned Stream Metadata: {args.need_scanned_stream_metadata}")
    print("=" * 60)

    decode(
        args.gpu_id,
        args.encoded_file_path,
        args.stats_file_path,
        args.use_device_memory,
        args.need_scanned_stream_metadata
    )