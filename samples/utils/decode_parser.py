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
Common argument parser for PyNvVideoCodec sample applications.
Provides standardized command-line arguments and parameter groups for different decoder types.

Available parameter groups:
- Basic: GPU ID, input/output files
- Decode: Device memory, frame count
- Low Latency: Decode latency modes
- Multi-instance: Number of instances, execution mode (thread/process)
"""
import argparse
from pathlib import Path
from typing import Optional, Union


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common arguments to an existing parser.

    Adds the following arguments:
        gpu_id (int): GPU device ID to use
        encoded_file_path (Path): Input video file path
        raw_file_path (Path): Output decoded file path
    """
    parser.add_argument(
        "-g", "--gpu_id",
        type=int,
        default=0,
        help="GPU ID to use (check nvidia-smi). Default: 0"
    )
    parser.add_argument(
        "-i", "--encoded_file_path",
        type=Path,
        required=True,
        help="Input encoded video file"
    )
    parser.add_argument(
        "-o", "--raw_file_path",
        type=Path,
        help="Output raw video file. Default: <input_name>.yuv"
    )

def add_decode_args(parser: argparse.ArgumentParser) -> None:
    """Add decoder-specific arguments to parser.

    Adds the following arguments:
        use_device_memory (int): Use GPU (1) or CPU (0) memory for output
        frame_count (int): Maximum number of frames to decode
    """
    parser.add_argument(
        "-d", "--use_device_memory",
        type=int,
        choices=[0, 1],
        default=1,
        help="Use device memory (1) or host memory (0). Default: 1"
    )
    parser.add_argument(
        "-f", "--frame_count",
        type=int,
        help="Maximum frames to decode. Default: all frames"
    )

def add_low_latency_args(parser: argparse.ArgumentParser) -> None:
    """Add low-latency specific arguments to parser.

    Adds the following arguments:
        decode_latency (int): Latency mode for decoding
            0: NATIVE - Standard 4-frame latency with display order output
            1: LOW - Zero frame latency with display order output
            2: ZERO - Zero frame latency with decode order output
    """
    parser.add_argument(
        "-dl", "--decode_latency",
        type=int,
        default=0,
        choices=[0, 1, 2],
        help="""Decoder latency mode:
        0 - NATIVE: 4 frame latency, output in display order
        1 - LOW: 0 frame latency, output in display order
        2 - ZERO: 0 frame latency, output in decode order"""
    )

def add_sei_args(parser: argparse.ArgumentParser) -> None:
    """Add SEI-specific arguments to parser.

    Adds the following arguments:
        sei_file_path (Path): Path to output file for SEI messages
    """
    parser.add_argument(
        "-s", "--sei_file_path",
        type=Path,
        default="sei_message.txt",
        help="SEI message output file (write to). Default: sei_message.txt"
    )

def add_stats_args(parser: argparse.ArgumentParser) -> None:
    """Add decode statistics specific arguments to parser.

    Adds the following arguments:
        stats_file_path (Path): Path to output file for decode statistics
    """
    parser.add_argument(
        "-p", "--stats_file_path",
        type=Path,
        help="Text file for parsed decode statistics. Default: <input_file_name>_stats.txt"
    )

def add_reconfigure_args(parser: argparse.ArgumentParser) -> None:
    """Add reconfigure-specific arguments to parser.

    Adds the following arguments:
        input_file1 (Path): First input encoded video file
        input_file2 (Path): Second input encoded video file
        raw_file_path1 (Path): First output raw video file
        raw_file_path2 (Path): Second output raw video file
    """
    parser.add_argument(
        "-i1", "--input_file1",
        type=Path,
        required=True,
        help="First input encoded video file"
    )
    parser.add_argument(
        "-i2", "--input_file2",
        type=Path,
        required=True,
        help="Second input encoded video file (with different dimensions)"
    )
    parser.add_argument(
        "-o1", "--raw_file_path1",
        type=Path,
        help="First output raw video file. Default: <input_file1_name>.yuv"
    )
    parser.add_argument(
        "-o2", "--raw_file_path2",
        type=Path,
        help="Second output raw video file. Default: <input_file2_name>.yuv"
    )

def add_detection_args(parser: argparse.ArgumentParser) -> None:
    """Add object detection specific arguments to parser.

    Adds the following arguments:
        detection_output_file_path (Path): Output file for detection results
        confidence_threshold (float): Confidence threshold for detections
        display_output (bool): Whether to display detection visualization
    """
    parser.add_argument(
        "-do", "--detection_output_file_path",
        type=Path,
        help="Detection output file path. Default: <input_file_name>_detection.txt"
    )
    parser.add_argument(
        "-c", "--confidence_threshold",
        type=float,
        default=0.8,
        help="Confidence score above which the bounding box and label is considered a valid detection"
    )
    parser.add_argument(
        "-d", "--display_output",
        action='store_true',
        help="Enable output display"
    )

def add_sampling_args(parser: argparse.ArgumentParser) -> None:
    """Add sampling-specific arguments to parser.

    Adds the following arguments:
        video_files (list): List of video files to process
        frames (int): Number of frames to sample per video
    """
    parser.add_argument(
        "video_files",
        nargs="+",
        type=str,
        help="Video files to process"
    )
    parser.add_argument(
        "-f", "--frames",
        type=int,
        default=8,
        help="Number of frames to sample per video (default: 8)"
    )

def add_scanned_metadata_args(parser: argparse.ArgumentParser) -> None:
    """Add scanned stream metadata arguments to parser.

    Adds the following arguments:
        need_scanned_stream_metadata (bool): Whether to scan stream for detailed metadata
            When enabled, provides access to frame-level information like keyframe locations.
            This requires scanning the entire stream upfront which adds initialization time.
    """
    parser.add_argument(
        "-sm", "--need_scanned_stream_metadata",
        action="store_true",
        default=False,
        help="Enable scanning stream for detailed metadata (keyframe locations, etc.). Default: False"
    )

def add_multi_instance_args(parser: argparse.ArgumentParser) -> None:
    """Add multi-instance specific arguments to parser.

    Adds the following arguments:
        num_instances (int): Number of parallel decoder instances to run
        mode (str): Execution mode for parallel decoding
            'thread': Use Python threading (shared memory space)
            'process': Use multiprocessing (separate memory spaces)
    """
    parser.add_argument(
        "-n", "--num_instances",
        type=int,
        default=1,
        help="Number of parallel decode instances to run. Default: 1"
    )
    parser.add_argument(
        "-m", "--mode",
        choices=['thread', 'process'],
        default='thread',
        help="Parallel execution mode: 'thread' for multithreading or 'process' for multiprocessing. Default: thread"
    )

def create_basic_parser(description: str) -> argparse.ArgumentParser:
    """Create a parser with common arguments."""
    parser = argparse.ArgumentParser(description=description)
    add_common_args(parser)
    return parser

def create_decode_parser(description: str) -> argparse.ArgumentParser:
    """Create a parser with common and decode-specific arguments."""
    parser = create_basic_parser(description)
    add_decode_args(parser)
    return parser

def parse_low_latency_args() -> argparse.Namespace:
    """Parse and validate arguments for low latency decode applications.

    Returns all decode_args plus:
        decode_latency (int): Latency mode (default: 0)
            0: NATIVE - 4 frame latency, display order
            1: LOW - 0 frame latency, display order
            2: ZERO - 0 frame latency, decode order
    """
    parser = create_decode_parser(
        "Low latency video decoding with NVIDIA GPU acceleration. "
        "Supports different latency modes for reduced decode delay and custom output ordering."
    )
    add_low_latency_args(parser)
    args = parser.parse_args()
    return convert_path_args(args)

def parse_multi_instance_args() -> argparse.Namespace:
    """Parse and validate arguments for multi-instance decode applications.

    Returns all decode_args plus:
        num_instances (int): Number of parallel decoders (default: 1)
        mode (str): Execution mode - 'thread' or 'process' (default: thread)
            thread: Uses Python threading for parallel decoding
            process: Uses multiprocessing for true parallel execution

    Note: This parser does not include output file argument as multi-instance apps
    are typically used for performance testing without file output.
    """
    parser = argparse.ArgumentParser(
        description="Multi-instance video decoding with NVIDIA GPU acceleration. "
        "Supports parallel decoding using multiple threads or processes for improved throughput."
    )
    # Add common args without output file
    parser.add_argument(
        "-g", "--gpu_id",
        type=int,
        default=0,
        help="GPU ID to use (check nvidia-smi). Default: 0"
    )
    parser.add_argument(
        "-i", "--encoded_file_path",
        type=Path,
        required=True,
        help="Input encoded video file"
    )
    # Add decode args
    add_decode_args(parser)
    # Add multi-instance args
    add_multi_instance_args(parser)
    args = parser.parse_args()

    # Convert input path to string and validate
    if hasattr(args, 'encoded_file_path') and args.encoded_file_path is not None:
        args.encoded_file_path = validate_input_file(args.encoded_file_path).as_posix()

    return args

def validate_input_file(file_path: Union[str, Path]) -> Path:
    """Validate that input file exists."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    return path

def get_output_path(input_path: Path, output_path: Optional[Path] = None, suffix: str = '.yuv') -> Path:
    """Get output path, using input path as base if output not specified."""
    if output_path is None:
        return input_path.with_suffix(suffix)
    return output_path

def convert_path_args(args: argparse.Namespace) -> argparse.Namespace:
    """Convert any Path objects in args to strings."""
    # Convert input path
    if hasattr(args, 'encoded_file_path') and args.encoded_file_path is not None:
        args.encoded_file_path = validate_input_file(args.encoded_file_path).as_posix()
    elif hasattr(args, 'input_file') and args.input_file is not None:
        args.encoded_file_path = validate_input_file(args.input_file).as_posix()
        delattr(args, 'input_file')  # Remove old attribute to standardize

    # Convert output path
    if hasattr(args, 'raw_file_path') and args.raw_file_path is not None:
        args.raw_file_path = Path(args.raw_file_path).as_posix()
    elif hasattr(args, 'yuv_file_path') and args.yuv_file_path is not None:
        args.raw_file_path = Path(args.yuv_file_path).as_posix()
        delattr(args, 'yuv_file_path')  # Remove old attribute to standardize

    # Set default output path if not provided
    if not hasattr(args, 'raw_file_path') or args.raw_file_path is None:
        input_path = Path(args.encoded_file_path)
        args.raw_file_path = input_path.with_suffix('.yuv').as_posix()

    return args

def create_stats_parser(description: str) -> argparse.ArgumentParser:
    """Create a parser specifically for SEI message extraction without raw file output."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "-g", "--gpu_id",
        type=int,
        default=0,
        help="GPU ID to use (check nvidia-smi). Default: 0"
    )
    parser.add_argument(
        "-i", "--encoded_file_path",
        type=Path,
        required=True,
        help="Input encoded video file"
    )
    parser.add_argument(
        "-d", "--use_device_memory",
        type=int,
        choices=[0, 1],
        default=1,
        help="Use device memory (1) or host memory (0). Default: 1"
    )
    parser.add_argument(
        "-p", "--stats_file_path",
        type=Path,
        help="Text file for parsed decode statistics. Default: <input_file_name>_stats.txt"
    )
    add_scanned_metadata_args(parser)
    return parser

def parse_stats_args(description: str = None) -> argparse.Namespace:
    """Parse and validate arguments for decode statistics extraction applications.

    Args:
        description (str, optional): Custom parser description. If None, uses default.

    Returns args with:
        gpu_id (int): GPU to use (default: 0)
        encoded_file_path (str): Input video file path
        use_device_memory (int): Use GPU memory (1) or CPU memory (0) (default: 1)
        stats_file_path (str): Path to output file for decode statistics (default: input_name_stats.txt)
    """
    if description is None:
        description = (
            "Video decoding with statistics extraction using NVIDIA GPU acceleration. "
            "Decodes input video and extracts detailed decode statistics to a separate file."
        )

    parser = create_stats_parser(description)
    args = parser.parse_args()

    # Set default stats file path if not provided
    if hasattr(args, 'stats_file_path'):
        if args.stats_file_path is None:
            input_path = Path(args.encoded_file_path)
            args.stats_file_path = input_path.parent / (input_path.stem + '_stats.txt')
        args.stats_file_path = args.stats_file_path.as_posix()

    # Convert input path to string and validate
    if hasattr(args, 'encoded_file_path') and args.encoded_file_path is not None:
        args.encoded_file_path = validate_input_file(args.encoded_file_path).as_posix()

    return args

def parse_reconfigure_args(description: str = None) -> argparse.Namespace:
    """Parse and validate arguments for decoder reconfiguration applications.

    Args:
        description (str, optional): Custom parser description. If None, uses default.

    Returns args with:
        input_file1 (str): First input encoded video file path
        input_file2 (str): Second input encoded video file path
        raw_file_path1 (str): First output decoded file path (default: input_file1_name.yuv)
        raw_file_path2 (str): Second output decoded file path (default: input_file2_name.yuv)
        gpu_id (int): GPU to use
        use_device_memory (int): Use GPU memory (1) or CPU memory (0)
        frame_count (int, optional): Number of frames to decode
    """
    if description is None:
        description = (
            "Video decoding with decoder reconfiguration using NVIDIA GPU acceleration. "
            "Decodes two input videos with different dimensions by reconfiguring the decoder."
        )

    # Create parser with only GPU argument, then add reconfigure-specific and decode args
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "-g", "--gpu_id",
        type=int,
        default=0,
        help="GPU ID to use (check nvidia-smi). Default: 0"
    )
    add_reconfigure_args(parser)
    add_decode_args(parser)
    args = parser.parse_args()

    # Convert paths to strings and validate for input_file1
    if hasattr(args, 'input_file1'):
        args.input_file1 = validate_input_file(args.input_file1).as_posix()
    if hasattr(args, 'raw_file_path1'):
        if args.raw_file_path1 is None:
            input_path = Path(args.input_file1)
            args.raw_file_path1 = input_path.with_suffix('.yuv').as_posix()
        else:
            args.raw_file_path1 = Path(args.raw_file_path1).as_posix()

    # Convert paths to strings and validate for input_file2
    if hasattr(args, 'input_file2'):
        args.input_file2 = validate_input_file(args.input_file2).as_posix()
    if hasattr(args, 'raw_file_path2'):
        if args.raw_file_path2 is None:
            input_path = Path(args.input_file2)
            args.raw_file_path2 = input_path.with_suffix('.yuv').as_posix()
        else:
            args.raw_file_path2 = Path(args.raw_file_path2).as_posix()

    return args

def parse_sei_args(description: str = None) -> argparse.Namespace:
    """Parse and validate arguments for SEI message extraction applications.

    Args:
        description (str, optional): Custom parser description. If None, uses default.

    Returns args with:
        gpu_id (int): GPU to use (default: 0)
        encoded_file_path (str): Input video file path
        use_device_memory (int): Use GPU memory (1) or CPU memory (0) (default: 1)
        sei_file_path (str): Path to output file for SEI messages (default: sei_message.bin)
    """
    if description is None:
        description = (
            "SEI message extraction using NVIDIA GPU acceleration. "
            "Extracts SEI messages from video stream without saving decoded frames."
        )

    parser = argparse.ArgumentParser(description=description)
    # Add basic arguments
    parser.add_argument(
        "-g", "--gpu_id",
        type=int,
        default=0,
        help="GPU ID to use (check nvidia-smi). Default: 0"
    )
    parser.add_argument(
        "-i", "--encoded_file_path",
        type=Path,
        required=True,
        help="Input encoded video file"
    )
    parser.add_argument(
        "-d", "--use_device_memory",
        type=int,
        choices=[0, 1],
        default=1,
        help="Use device memory (1) or host memory (0). Default: 1"
    )
    # Add SEI-specific argument
    parser.add_argument(
        "-s", "--sei_file_path",
        type=Path,
        default="sei_message.bin",
        help="SEI message output file (write to). Default: sei_message.bin. Sei type message is written to sei_type_message.bin"
    )
    parser.add_argument(
        "-st", "--sei_type_file_path",
        type=Path,
        default="sei_type_message.bin",
        help="SEI type message output file (write to). Default: sei_type_message.bin"
    )
    args = parser.parse_args()

    # Convert paths to strings and validate
    args.encoded_file_path = validate_input_file(args.encoded_file_path).as_posix()
    args.sei_file_path = Path(args.sei_file_path).as_posix()
    args.sei_type_file_path = Path(args.sei_type_file_path).as_posix()
    return args

def parse_detection_args(description: str = None) -> argparse.Namespace:
    """Parse and validate arguments for object detection applications.

    Args:
        description (str, optional): Custom parser description. If None, uses default.

    Returns args with:
        gpu_id (int): GPU to use (default: 0)
        encoded_file_path (str): Input video file path
        detection_output_file_path (str): Output file for detection results (-do flag)
        confidence_threshold (float): Confidence threshold (default: 0.8)
        display_output (bool): Whether to display visualization
    """
    if description is None:
        description = (
            "Object detection using PyNvVideoCodec's ThreadedDecoder. "
            "Uses FasterRCNN model to detect objects in video frames with zero-copy tensor interop."
        )

    parser = create_basic_parser(description)
    add_detection_args(parser)
    args = parser.parse_args()

    # Set default detection output path if not provided
    if args.detection_output_file_path is None:
        input_path = Path(args.encoded_file_path)
        args.detection_output_file_path = input_path.with_name(f"{input_path.stem}_detection.txt")

    return convert_path_args(args)

def parse_sampling_args(description: str = None) -> tuple:
    """Parse and validate arguments for video sampling applications.

    Args:
        description (str, optional): Custom parser description. If None, uses default.

    Returns:
        tuple: (args, valid_files) where:
            args: Namespace with:
                gpu_id (int): GPU to use (default: 0)
                frames (int): Frames to sample per video (default: 8)
                video_files (list): List of video files to process
            valid_files (list): List of validated video file paths
    """
    if description is None:
        description = (
            "Video frame sampling with NVIDIA GPU acceleration. "
            "Samples evenly distributed frames from multiple video files."
        )

    parser = argparse.ArgumentParser(
        description=description,
        epilog="""
Examples:
  %(prog)s video1.mp4 video2.mp4 video3.mp4    # Process multiple specific files
  %(prog)s /path/to/videos/*.mp4                # Process all MP4 files in directory
  %(prog)s video.mp4 -g 1 -f 16                # Use GPU 1 and sample 16 frames per video
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-g", "--gpu_id",
        type=int,
        default=0,
        help="GPU ID to use (check nvidia-smi). Default: 0"
    )
    add_sampling_args(parser)
    add_scanned_metadata_args(parser)
    args = parser.parse_args()

    # Validate video files
    valid_files = []
    for video_file in args.video_files:
        try:
            valid_files.append(validate_input_file(video_file))
        except FileNotFoundError:
            print(f"Warning: File not found: {video_file}")

    if not valid_files:
        raise FileNotFoundError("No valid video files found")

    # Check MUSA/CUDA availability
    import torch
    try:
        import torch_musa  # noqa: F401 - registers the MUSA backend with torch
    except ImportError:
        torch_musa = None

    if hasattr(torch, "musa") and torch.musa.is_available():
        device_count = torch.musa.device_count()
        backend = "MUSA"
    elif torch.cuda.is_available():
        device_count = torch.cuda.device_count()
        backend = "CUDA"
    else:
        raise RuntimeError("Neither MUSA nor CUDA is available. This application requires a GPU backend.")

    # Validate GPU ID
    if args.gpu_id >= device_count:
        raise ValueError(f"GPU ID {args.gpu_id} not available for {backend}. Available GPUs: 0-{device_count-1}")

    return args, valid_files

def parse_decode_args(description: str = None) -> argparse.Namespace:
    """Parse and validate command line arguments for decode applications.

    Args:
        description (str, optional): Custom parser description. If None, uses default.

    Returns args with:
        gpu_id (int): GPU to use (default: 0)
        encoded_file_path (str): Input video file path
        raw_file_path (str): Output decoded file path (default: input_name.yuv)
        use_device_memory (int): Use GPU memory (1) or CPU memory (0) (default: 1)
        frame_count (int, optional): Number of frames to decode (default: all)
    """
    if description is None:
        description = (
            "Video decoding with NVIDIA GPU acceleration. "
            "Decodes input video to raw format with configurable GPU/CPU memory usage and frame limits."
        )

    parser = create_decode_parser(description)
    args = parser.parse_args()
    return convert_path_args(args)
