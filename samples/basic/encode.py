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
This sample demonstrates unified video encoding with support for both CPU and GPU buffer modes.
It shows how to:
1. Configure and use different buffer modes for encoding
2. Handle both host (CPU) and device (GPU) memory efficiently
3. Manage encoder resources and states
4. Process frames with optimal memory handling

The sample supports two buffer modes:
- CPU Buffer Mode:
  * Uses host memory for frame data

- GPU Buffer Mode:
  * Uses device memory for frame data

Usage:
    python encode.py -i <input_file> -s <size> -m <mode> [options]

Example:
    python encode.py -i input.yuv -s 1920x1080 -m gpu

Arguments:
    -i: Raw input video file
    -s: Frame size (e.g., 1920x1080)
    -m: Buffer mode (cpu/gpu)
    -if: Input format (default: NV12)
    -c: Codec (H264, HEVC, AV1)
    -f: Number of frames (default: all)
    -g: GPU ID (default: 0)
    -json: Encoder config file

'''

import PyNvVideoCodec as nvc
import numpy as np
import json
import argparse
from pathlib import Path
import os
import sys
from os.path import join, dirname, abspath

# Add the parent directory to Python path in a way that works from any working directory
current_dir = dirname(abspath(__file__))
parent_dir = dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Import utilities for GPU buffer mode
try:
    from utils.Utils import AppFrame, FetchCPUFrame, FetchGPUFrame
    GPU_UTILS_AVAILABLE = True
except ImportError:
    GPU_UTILS_AVAILABLE = False
    print("Warning: Utils module not found. GPU buffer mode will be disabled.")


# Import utilities for frame handling
from utils.frame_utils import get_frame_size
from utils.encode_parser import parse_unified_args


def encode_cpu_buffer(gpu_id, dec_file_path, enc_file_path, width, height, fmt, config_params, frame_count):
    """
    Encode frames using host memory buffers as input.

    This function reads image data from a file and copies it to CUDA buffers for encoding.
    The encoder submits the data to NVENC hardware for encoding. Video memory buffer is
    allocated to get the NVENC hardware output. The output is copied from video memory
    to host memory for file storage.

    Parameters:
        gpu_id (int): Ordinal of GPU to use
        dec_file_path (str): Path to file to be decoded
        enc_file_path (str): Path to output file for encoded frames
        width (int): Width of encoded frame
        height (int): Height of encoded frame
        fmt (str): Surface format string in uppercase (e.g., "NV12")
        config_params (dict): Key-value pairs providing fine-grained control on encoding
        frame_count (int): Number of frames to encode

    Returns:
        None
    """
    print("Using CPU buffer mode")
    
    frame_size = get_frame_size(width, height, fmt)
    with open(dec_file_path, "rb") as dec_file, open(enc_file_path, "wb") as enc_file:
        config_params["gpu_id"] = gpu_id
        nvenc = nvc.CreateEncoder(width, height, fmt, True, **config_params)  # True = use CPU buffers
        
        # Calculate total available frames from file size
        file_size = os.path.getsize(dec_file_path)
        available_frames = file_size // frame_size
        
        # Determine frames to process with limit
        frames_to_process = frame_count if frame_count > 0 else available_frames
        frames_to_process = min(frames_to_process, available_frames)
        
        print(f"File contains {available_frames} frames, processing {frames_to_process} frames using CPU buffers...")
        
        frames_encoded = 0
        for i in range(frames_to_process):
            chunk = np.fromfile(dec_file, np.uint8, count=frame_size)
            if chunk.size != 0:
                bitstream = nvenc.Encode(chunk)
                enc_file.write(bytearray(bitstream))
                frames_encoded += 1
            else:
                print(f"Warning: Could not read frame {i+1}")
                break
        
        # Flush encoder queue
        bitstream = nvenc.EndEncode()
        enc_file.write(bytearray(bitstream))
        print(f"Completed encoding {frames_encoded} frames using CPU buffers")
        print(f"Output file: {enc_file_path}")


def encode_gpu_buffer(gpu_id, dec_file_path, enc_file_path, width, height, fmt, config_params, frame_count):
    """
    Encode frames using CUDA device buffers as input.

    This function reads image data from a file and loads it to CUDA input buffers using
    FetchGPUFrame(). The encoder copies the CUDA buffers and submits them to NVENC hardware
    for encoding. Video memory buffer is allocated to get the NVENC hardware output.
    The output is copied from video memory to host memory for file storage.

    Parameters:
        gpu_id (int): Ordinal of GPU to use
        dec_file_path (str): Path to file to be decoded
        enc_file_path (str): Path to output file for encoded frames
        width (int): Width of encoded frame
        height (int): Height of encoded frame
        fmt (str): Surface format string in uppercase (e.g., "NV12")
        config_params (dict): Key-value pairs providing fine-grained control on encoding
        frame_count (int): Number of frames to encode

    Returns:
        None
    """
    print("Using GPU buffer mode")
    
    if not GPU_UTILS_AVAILABLE:
        raise RuntimeError("GPU buffer mode requires Utils module (AppFrame, FetchCPUFrame, FetchGPUFrame)")
    
    # Show encoder capabilities
    caps = nvc.GetEncoderCaps(codec=config_params["codec"])
    if "num_encoder_engines" in caps:
        print(f"Number of NVENCs: {caps['num_encoder_engines']}")

    with open(dec_file_path, "rb") as decFile, open(enc_file_path, "wb") as encFile:
        config_params["gpu_id"] = gpu_id
        nvenc = nvc.CreateEncoder(width, height, fmt, False, **config_params)  # False = use GPU buffers
        input_frame_list = [AppFrame(width, height, fmt) for _ in range(1, 5)]
        
        # Calculate total available frames from file size
        file_size = os.path.getsize(dec_file_path)
        available_frames = file_size // input_frame_list[0].frameSize
        
        # Determine frames to process with limit
        frames_to_process = frame_count if frame_count > 0 else available_frames
        frames_to_process = min(frames_to_process, available_frames)
        
        
        print(f"File contains {available_frames} frames, processing {frames_to_process} frames using GPU buffers...")
        
        for input_gpu_frame in FetchGPUFrame(
            input_frame_list,
            FetchCPUFrame(decFile, input_frame_list[0].frameSize),
            frames_to_process
        ):
            bitstream = nvenc.Encode(input_gpu_frame)
            bitstream = bytearray(bitstream)
            encFile.write(bitstream)
        
        # Flush encoder queue
        bitstream = nvenc.EndEncode()
        bitstream = bytearray(bitstream)
        encFile.write(bitstream)
    
    print(f"Completed encoding {frames_to_process} frames using GPU buffers")
    print(f"Output file: {enc_file_path}")


def encode_unified(gpu_id, dec_file_path, enc_file_path, width, height, fmt, config_params, frame_count, buffer_mode):
    """
    Unified encoding function that supports both CPU and GPU buffer modes.

    Parameters:
        gpu_id (int): Ordinal of GPU to use
        dec_file_path (str): Path to file to be decoded
        enc_file_path (str): Path to output file for encoded frames
        width (int): Width of encoded frame
        height (int): Height of encoded frame
        fmt (str): Surface format string in uppercase (e.g., "NV12")
        config_params (dict): Key-value pairs providing fine-grained control on encoding
        frame_count (int): Number of frames to encode
        buffer_mode (str): Buffer mode - "cpu" or "gpu"

    Returns:
        None
    """
    try:
        if buffer_mode.lower() == "cpu":
            encode_cpu_buffer(gpu_id, dec_file_path, enc_file_path, width, height, fmt, config_params, frame_count)
        elif buffer_mode.lower() == "gpu":
            encode_gpu_buffer(gpu_id, dec_file_path, enc_file_path, width, height, fmt, config_params, frame_count)
        else:
            raise ValueError(f"Invalid buffer mode: {buffer_mode}. Must be 'cpu' or 'gpu'")
            
    except nvc.PyNvVCExceptionUnsupported as e:
        print(f"CreateEncoder failure: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def validate_gpu_mode(args) -> None:
    """Validate GPU buffer mode requirements."""
    if args.buffer_mode == "gpu" and not GPU_UTILS_AVAILABLE:
        print("Error: GPU buffer mode requires Utils module, but it's not available.")
        print("Please use CPU buffer mode (-m cpu) or ensure Utils module is accessible.")
        sys.exit(1)


if __name__ == "__main__":
    args = parse_unified_args(
        "Unified encoding application supporting both CPU and GPU buffer modes."
    )

    # Display configuration
    print("=" * 60)
    print("ENCODER CONFIGURATION")
    print("=" * 60)
    print(f"Buffer mode: {args.buffer_mode.upper()}")
    print(f"Input file: {args.raw_file_path}")
    print(f"Output file: {args.encoded_file_path}")
    print(f"Resolution: {args.width}x{args.height}")
    print(f"Format: {args.format}")
    print(f"Codec: {args.codec}")
    print(f"GPU ID: {args.gpu_id}")
    print(f"Frame count: {args.frame_count if args.frame_count > 0 else 'All frames'}")
    print("=" * 60)

    # Validate GPU mode requirements
    validate_gpu_mode(args)
    
    # Run encoding
    encode_unified(
        args.gpu_id,
        args.raw_file_path.as_posix(),
        args.encoded_file_path.as_posix(),
        args.width,
        args.height,
        args.format,
        args.config,
        args.frame_count,
        args.buffer_mode
    )

    print("=" * 60)
    print("ENCODING COMPLETE")
    print("=" * 60)
