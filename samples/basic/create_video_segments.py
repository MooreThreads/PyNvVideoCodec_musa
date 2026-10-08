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
This sample demonstrates video segmentation which can be useful for creating training data for machine learning models.
It shows how to:
1. Extract segments from a video file based on timestamp ranges
2. Use the SimpleDecoder to get video metadata
3. Configure and use the Transcoder for segment extraction
4. Handle multiple output segments with proper naming

Usage:
    python create_video_segments.py -i <input_file> [options]

Example:
    python create_video_segments.py -i input.mp4 -s segments.txt -c config.json

Arguments:
    -i: Input video file
    -s: Segments file (default: segments.txt)
    -c: Transcoder config file (default: transcode_config.json)
    -o: Output filename template
    -g: GPU ID (default: 0)

Segments File Format:
    start_time end_time
    Example:
        0.0 10.5
        15.0 30.0
        45.5 60.0

Output file format:
    This is the default output template. The file name can be customized using the -o argument. Time stamp is appended to the file name.
    {input_file_name}_segment_{start_time}_{end_time}.mp4
    Example:
        input_file_name_segment_0.0_10.5.mp4
        input_file_name_segment_15.0_30.0.mp4
        input_file_name_segment_45.5_60.0.mp4

Note: Times are in seconds. Each segment is validated against video duration.
'''

import json
import os
import sys
from os.path import dirname, abspath
import PyNvVideoCodec as nvc


# Add the parent directory to Python path in a way that works from any working directory
current_dir = dirname(abspath(__file__))
parent_dir = dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from utils.transcode_parser import parse_transcode_args


def get_video_duration(input_file_path: str, gpu_id: int) -> float:
    """Get video duration in seconds."""
    try:
        decoder = nvc.SimpleDecoder(input_file_path, gpu_id=gpu_id)
        duration = decoder.get_stream_metadata().duration
        print(f"Video duration: {duration:.2f} seconds")
        return duration
    except Exception as e:
        print(f"Error getting video duration: {e}")
        return 0.0


def create_video_segments(input_file_path: str, segments_file_path: str,
                         config_file_path: str, output_template: str, gpu_id: int):
    """Create video segments from input file based on segments text file."""
    
    # Get video duration for validation
    duration = get_video_duration(input_file_path, gpu_id)
    if duration <= 0:
        print("Error: Could not determine video duration")
        return
    
    # Load transcoder configuration
    with open(config_file_path) as json_file:
        config = json.load(json_file)
    
    input_file_name_base = os.path.splitext(os.path.basename(input_file_path))[0]
    successful_segments = 0
    
    # Process segments file
    with open(segments_file_path, 'r') as file:
        for line_num, line in enumerate(file, 1):
            line = line.strip()
            if not line:  # Skip empty lines
                continue
                
            try:
                start_ts_str, end_ts_str = line.split()
                start_time = float(start_ts_str)
                end_time = float(end_ts_str)
                
                # Error check: end timestamp should not exceed media duration
                if end_time > duration:
                    print(f"Warning: Line {line_num}: End time {end_time:.2f}s exceeds video duration {duration:.2f}s - clipping to duration")
                    end_time = duration
                
                if start_time >= end_time:
                    print(f"Error: Line {line_num}: Invalid time range {start_time}-{end_time}")
                    continue
                
                # Generate output path
                base_output_path = output_template.format(input_file_name=input_file_name_base)
                base_output_name, base_output_ext = os.path.splitext(base_output_path)
                if not base_output_ext:
                    base_output_ext = '.mp4'
                    base_output_path = base_output_name + base_output_ext
                
                start_time = round(start_time, 2)
                end_time = round(end_time, 2)
                print(f"Creating segment: {start_time:g}s - {end_time:g}s")
                
                # Create transcoder and generate segment
                transcoder = nvc.Transcoder(input_file_path, base_output_path, gpu_id, 0, 0, **config)
                transcoder.segmented_transcode(start_time, end_time)
                
                # Expected output filename (API appends timestamps)
                final_output = f"{base_output_name}_{start_time:g}_{end_time:g}{base_output_ext}"
                print(f"✓ Created: {final_output}")
                successful_segments += 1
                
            except ValueError as e:
                print(f"Error: Line {line_num}: Invalid format '{line}' - {e}")
            except Exception as e:
                print(f"Error: Line {line_num}: Failed to create segment - {e}")
    
    print(f"\nSummary: {successful_segments} segments created successfully")


def main():
    args = parse_transcode_args("Create video segments from text file input")
    
    # Display configuration
    print("=" * 60)
    print("VIDEO SEGMENTATION CONFIGURATION")
    print("=" * 60)
    print(f"Input: {args.input_file_path}")
    print(f"Segments File: {args.segments_file_path}")
    print(f"Config File: {args.config_file_path}")
    print(f"GPU ID: {args.gpu_id}")
    print("=" * 60)
    
    # Validate files exist
    for file_path, name in [(args.input_file_path, "Input video"), 
                           (args.segments_file_path, "Segments file"), 
                           (args.config_file_path, "Config file")]:
        if not os.path.exists(file_path):
            print(f"Error: {name} not found: {file_path}")
            return
    
    create_video_segments(args.input_file_path, args.segments_file_path, args.config_file_path, 
                         args.output_template, args.gpu_id)
    
    print("=" * 60)
    print("SEGMENTATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
