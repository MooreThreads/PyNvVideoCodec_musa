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
This sample demonstrates multi-file video decoding with frame sampling and tensor conversion.
It shows how to:
1. Process multiple video files efficiently
2. Sample frames evenly across videos
3. Convert video frames to PyTorch tensors
4. Handle decoder reconfiguration

Key Learning Outcomes:
- Reconfigure decoder instance to process multiple video files
- RGB color format output
- PyTorch tensor conversion
- CUDA device memory usage


Usage:
    python simple_decode_sampling.py video1.mp4 video2.mp4 [options]
    python simple_decode_sampling.py /path/to/videos/*.mp4 [options]

Example:
    python simple_decode_sampling.py video1.mp4 video2.mp4 -g 0 -f 16

Arguments:
    video_files: One or more video files to process
    -g/--gpu-id: GPU device ID (default: 0)
    -f/--frames: Frames to sample per video (default: 8)

Note: Frames are sampled evenly across each video's duration.
'''

import sys
import torch
try:
    import torch_musa  # noqa: F401 - registers the MUSA backend with torch
except ImportError:
    torch_musa = None
import PyNvVideoCodec as nvc
import numpy as np
from typing import List
from os.path import dirname, abspath

# Add the parent directory to Python path in a way that works from any working directory
current_dir = dirname(abspath(__file__))
parent_dir = dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Import utilities for decoding
from utils.Utils import convert_frames_to_torch
from utils.decode_parser import parse_sampling_args


def get_device_name(gpu_id: int) -> str:
    if hasattr(torch, "musa") and torch.musa.is_available():
        return torch.musa.get_device_name(gpu_id)
    if torch.cuda.is_available():
        return torch.cuda.get_device_name(gpu_id)
    return "MUSA/CUDA device unavailable to torch"


def synchronize_device_stream() -> None:
    if hasattr(torch, "musa") and torch.musa.is_available():
        torch.musa.current_stream().synchronize()
    elif torch.cuda.is_available():
        torch.cuda.current_stream().synchronize()

def process_multiple_files(video_files: List[str], gpu_id: int = 0, num_frames: int = 8,
                          need_scanned_stream_metadata: bool = False) -> None:
    """
    Process multiple video files using decoder reconfiguration.

    Args:
        video_files: List of video file paths
        gpu_id: GPU device ID to use
        num_frames: Number of frames to decode per video
        need_scanned_stream_metadata: Whether to scan stream for detailed metadata
    """
    if not video_files:
        print("No video files provided")
        return

    decoder = None

    try:
        for i, video_file in enumerate(video_files):
            # Convert Path to string if needed
            video_path = str(video_file)

            print(f"\n{'='*60}")
            print(f"Processing file {i+1}/{len(video_files)}: {video_path}")
            print(f"{'='*60}")

            if i == 0:
                # Create decoder from first file
                print(f"Creating decoder for: {video_path}")
                decoder = nvc.SimpleDecoder(
                    video_path,
                    gpu_id=gpu_id,
                    use_device_memory=True,
                    need_scanned_stream_metadata=need_scanned_stream_metadata,
                    output_color_type=nvc.OutputColorType.RGB,  # RGB format
                    max_width=2048,
                    max_height=2048
                )
                print(f"Decoder created successfully. Total frames: {len(decoder)}")
            else:
                # Reconfigure decoder for subsequent files
                print(f"Reconfiguring decoder for: {video_path}")
                synchronize_device_stream()
                decoder.reconfigure_decoder(video_path)
                print(f"Decoder reconfigured successfully. Total frames: {len(decoder)}")

            # Get total frames and calculate indices
            total_frames = len(decoder)

            if total_frames == 0:
                print(f"Warning: No frames found in video: {video_file}")
                continue

            # Sample frames evenly across the video
            frame_indices = np.linspace(0, total_frames-1, num_frames, dtype=int).tolist()

            print(f"Decoding {num_frames} frames from indices: {frame_indices}")

            # Get batch of frames by indices
            decoded_frames = decoder.get_batch_frames_by_index(frame_indices)

            # Convert to torch tensor
            frames_tensor = convert_frames_to_torch(decoded_frames)

            print(f"Decoded frames shape: {frames_tensor.shape}")

            # Clean up frames to free memory
            del frames_tensor
            del decoded_frames

        print(f"\n{'='*60}")
        print("All files processed successfully!")
        print(f"{'='*60}")

    except Exception as e:
        print(f"Error processing files: {e}")
        raise
    finally:
        # Clean up decoder
        if decoder is not None:
            del decoder
def main():
    """Main application entry point"""
    try:
        args, valid_files = parse_sampling_args()

        # Display configuration
        print("=" * 60)
        print("VIDEO SAMPLING CONFIGURATION")
        print("=" * 60)
        print(f"GPU: {args.gpu_id} ({get_device_name(args.gpu_id)})")
        print(f"Input Files: {len(valid_files)} files found")
        print(f"Frames per Video: {args.frames}")
        print(f"Need Scanned Stream Metadata: {args.need_scanned_stream_metadata}")
        print("=" * 60)

        # Process all files
        process_multiple_files(valid_files, args.gpu_id, args.frames, args.need_scanned_stream_metadata)

        print("=" * 60)
        print("SAMPLING COMPLETE")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\nApplication interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Application error: {e}")
        sys.exit(1)
if __name__ == "__main__":
    main()