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

"""
Helper module for parsing encoder command line arguments.

This module provides standardized argument parsing for encoder sample applications.
"""

import argparse
from pathlib import Path
from os.path import join, dirname
import json
import PyNvVideoCodec as nvc


# Maximum frames for performance testing to avoid OOM
PERF_MAX_FRAMES = 1000

def add_encode_args(parser: argparse.ArgumentParser, enforce_frame_limit: bool = False) -> None:
    """Add common encoder arguments to parser.

    Args:
        parser: The argument parser to add arguments to
        enforce_frame_limit: If True, enforces max frame limit for perf testing
    """
    parser.add_argument(
        "-g", "--gpu_id",
        type=int,
        default=0,
        help="Check nvidia-smi for available GPUs. Default: 0"
    )
    parser.add_argument(
        "-i", "--raw_file_path",
        type=Path,
        required=True,
        help="Raw video file to encode"
    )
    parser.add_argument(
        "-o", "--encoded_file_path",
        type=Path,
        help="Encoded video file (write to). Default: <input_file_name>.<codec>"
    )
    parser.add_argument(
        "-s", "--size",
        type=str,
        required=True,
        help="WidthxHeight of raw frame (e.g., 1920x1080)"
    )
    parser.add_argument(
        "-if", "--format",
        type=str,
        default="NV12",
        help="Format of input file. Default: NV12"
    )
    parser.add_argument(
        "-c", "--codec",
        type=str,
        help="Video codec (HEVC, H264, AV1). If not specified, uses the codec from config file."
    )
    parser.add_argument(
        "-json", "--config_file",
        type=str,
        default=join(dirname(dirname(__file__)), "advanced", "encode_config.json"),
        help="Path of JSON config file (default: encode_config.json in samples directory)"
    )
    help_text = "Number of frames to encode (0 for all frames). Default: 0"
    if enforce_frame_limit:
        help_text = f"Number of frames to encode (0-{PERF_MAX_FRAMES}, required for perf testing). Default: {PERF_MAX_FRAMES}"

    parser.add_argument(
        "-f", "--frame_count",
        type=int,
        default=PERF_MAX_FRAMES if enforce_frame_limit else 0,
        help=help_text
    )

def add_parallel_args(parser: argparse.ArgumentParser) -> None:
    """Add parallel processing arguments to parser."""
    parser.add_argument(
        "-m", "--mode",
        type=str,
        choices=["thread", "process"],
        default="thread",
        help="Parallel execution mode: 'thread' or 'process'"
    )
    parser.add_argument(
        "-n", "--num_workers",
        type=int,
        default=1,
        help="Number of parallel threads/processes. Default: 1"
    )

def load_config(args) -> dict:
    """Load and process encoder configuration from JSON file and command line args."""
    config = {}
    if args.config_file:
        with open(args.config_file) as jsonFile:
            config = json.loads(jsonFile.read())
            config["preset"] = config["preset"].upper()

    # Set codec (use h264 as default if not specified)
    args.codec = args.codec.lower() if args.codec is not None else "h264"
    config["codec"] = args.codec

    # Add GPU ID to config
    config["gpu_id"] = args.gpu_id

    # Process format
    args.format = args.format.upper()

    # Parse size
    width, height = map(int, args.size.split("x"))
    args.width = width
    args.height = height

    # Set default encoded_file_path if not provided (auto-generate from input file)
    if not hasattr(args, 'encoded_file_path') or args.encoded_file_path is None:
        args.encoded_file_path = args.raw_file_path.with_suffix(f'.{args.codec}')

    return config

def add_unified_args(parser: argparse.ArgumentParser) -> None:
    """Add unified encoder specific arguments to parser."""
    parser.add_argument(
        "-m", "--buffer_mode",
        type=str,
        choices=["cpu", "gpu"],
        default="gpu",
        help="Buffer mode: 'cpu' for host memory buffers, 'gpu' for CUDA device buffers. Default: gpu"
    )


def parse_perf_args(description: str = None) -> argparse.Namespace:
    """Parse arguments for performance testing applications.

    These apps require frame count limits to prevent OOM errors.
    Note: No output file argument as perf apps only measure performance without file output.
    """
    parser = argparse.ArgumentParser(description=description)

    # Add args manually without output file
    parser.add_argument(
        "-g", "--gpu_id",
        type=int,
        default=0,
        help="Check nvidia-smi for available GPUs. Default: 0"
    )
    parser.add_argument(
        "-i", "--raw_file_path",
        type=Path,
        required=True,
        help="Raw video file to encode"
    )
    parser.add_argument(
        "-s", "--size",
        type=str,
        required=True,
        help="WidthxHeight of raw frame (e.g., 1920x1080)"
    )
    parser.add_argument(
        "-if", "--format",
        type=str,
        default="NV12",
        help="Format of input file. Default: NV12"
    )
    parser.add_argument(
        "-c", "--codec",
        type=str,
        help="Video codec (HEVC, H264, AV1). If not specified, uses the codec from config file."
    )
    parser.add_argument(
        "-json", "--config_file",
        type=str,
        default=join(dirname(dirname(__file__)), "advanced", "encode_config.json"),
        help="Path of JSON config file (default: encode_config.json in samples directory)"
    )
    parser.add_argument(
        "-f", "--frame_count",
        type=int,
        default=PERF_MAX_FRAMES,
        help=f"Number of frames to encode (0-{PERF_MAX_FRAMES}, required for perf testing). Default: {PERF_MAX_FRAMES}"
    )

    add_parallel_args(parser)
    args = parser.parse_args()

    # Enforce frame limit for perf testing
    if args.frame_count > PERF_MAX_FRAMES:
        print(f"\nWarning: Requested {args.frame_count} frames exceeds limit. Using {PERF_MAX_FRAMES} frames.")
        args.frame_count = PERF_MAX_FRAMES
    elif args.frame_count <= 0:
        args.frame_count = PERF_MAX_FRAMES

    # Set encoded_file_path to None for perf apps (no output)
    args.encoded_file_path = None

    args.config = load_config(args)
    return args


def parse_unified_args(description: str = None) -> argparse.Namespace:
    """Parse arguments for unified encoding applications.

    These apps support unlimited frame counts and both CPU/GPU buffer modes.
    """
    parser = argparse.ArgumentParser(description=description)
    add_unified_args(parser)
    add_encode_args(parser, enforce_frame_limit=False)
    args = parser.parse_args()
    args.config = load_config(args)
    return args

def parse_sei_encode_args(description: str = None) -> argparse.Namespace:
    """Parse arguments for SEI encoding applications.

    These apps use GPU buffer mode only and support unlimited frame counts.
    Note: No buffer mode argument as these apps only support GPU buffer mode.
    """
    parser = argparse.ArgumentParser(description=description)

    # Add encode args manually without buffer mode
    parser.add_argument(
        "-g", "--gpu_id",
        type=int,
        default=0,
        help="Check nvidia-smi for available GPUs. Default: 0"
    )
    parser.add_argument(
        "-i", "--raw_file_path",
        type=Path,
        required=True,
        help="Raw video file to encode"
    )
    parser.add_argument(
        "-o", "--encoded_file_path",
        type=Path,
        help="Encoded video file (write to). Default: <input_file_name>.<codec>"
    )
    parser.add_argument(
        "-s", "--size",
        type=str,
        required=True,
        help="WidthxHeight of raw frame (e.g., 1920x1080)"
    )
    parser.add_argument(
        "-if", "--format",
        type=str,
        default="NV12",
        help="Format of input file. Default: NV12"
    )
    parser.add_argument(
        "-c", "--codec",
        type=str,
        help="Video codec (HEVC, H264, AV1). If not specified, uses the codec from config file."
    )
    parser.add_argument(
        "-json", "--config_file",
        type=str,
        default=join(dirname(dirname(__file__)), "advanced", "encode_config.json"),
        help="Path of JSON config file (default: encode_config.json in samples directory)"
    )
    parser.add_argument(
        "-f", "--frame_count",
        type=int,
        default=0,
        help="Number of frames to encode (0 for all frames). Default: 0"
    )

    args = parser.parse_args()
    args.config = load_config(args)
    return args

def parse_reconfigure_encode_args(description: str = None) -> argparse.Namespace:
    """Parse arguments for encoder reconfiguration applications.

    These apps use GPU buffer mode only and support unlimited frame counts.
    Note: No buffer mode argument as these apps only support GPU buffer mode.
    """
    parser = argparse.ArgumentParser(description=description)

    # Add encode args without buffer mode
    parser.add_argument(
        "-g", "--gpu_id",
        type=int,
        default=0,
        help="Check nvidia-smi for available GPUs. Default: 0"
    )
    parser.add_argument(
        "-i", "--raw_file_path",
        type=Path,
        required=True,
        help="Raw video file to encode"
    )
    parser.add_argument(
        "-o", "--encoded_file_path",
        type=Path,
        help="Encoded video file (write to). Default: <input_file_name>.<codec>"
    )
    parser.add_argument(
        "-s", "--size",
        type=str,
        required=True,
        help="WidthxHeight of raw frame (e.g., 1920x1080)"
    )
    parser.add_argument(
        "-if", "--format",
        type=str,
        default="NV12",
        help="Format of input file. Default: NV12"
    )
    parser.add_argument(
        "-c", "--codec",
        type=str,
        help="Video codec (HEVC, H264, AV1). If not specified, uses the codec from config file."
    )
    parser.add_argument(
        "-json", "--config_file",
        type=str,
        default=join(dirname(dirname(__file__)), "advanced", "encode_config_lowlatency.json"),
        help="Path of JSON config file (default: encode_config_lowlatency.json in samples directory)"
    )
    parser.add_argument(
        "-f", "--frame_count",
        type=int,
        default=0,
        help="Number of frames to encode (0 for all frames). Default: 0"
    )

    args = parser.parse_args()
    args.config = load_config(args)
    return args


