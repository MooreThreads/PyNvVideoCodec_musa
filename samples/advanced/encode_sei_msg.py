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
This sample demonstrates SEI (Supplemental Enhancement Information) message insertion during encoding.
It shows how to:
1. Create and format SEI messages
2. Insert SEI data into the encoded bitstream
3. Handle codec-specific SEI types
4. Manage message timing and placement

SEI messages are additional data embedded in video streams that provide supplementary information:
- HDR/Display Metadata: Color volume, light levels, and transfer characteristics for HDR content
- Timecode Data: Frame timing and sequence information
- Custom Metadata: User-defined data for application-specific needs

Common Use Cases:
- Video Playback: HDR display configuration and color management
- Content Creation: Frame accurate editing and post-processing
- Broadcast: Timing synchronization and content identification
- Custom Applications: Embedding application-specific metadata in the video stream

Usage:
    python encode_sei_msg.py -i <input_file> -s <size> [options]

Example:
    python encode_sei_msg.py -i input.yuv -o output.h264 -s 1920x1080

Arguments:
    -i: Raw input video file
    -o: Output encoded file (optional, default: <input_name>.<codec>)
    -s: Frame size (e.g., 1920x1080)
    -if: Input format (default: NV12)
    -c: Codec (H264, HEVC, AV1)
    -f: Number of frames (default: all)
    -g: GPU ID (default: 0)
    -json: Encoder config file

'''

import PyNvVideoCodec as nvc
import sys
import os
from os.path import dirname, abspath

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

from utils.encode_parser import parse_sei_encode_args
SEI_MESSAGE_1 = [0xdc, 0x45, 0xe9, 0xbd, 0xe6, 0xd9, 0x48, 0xb7, 0x96, 0x2c, 0xd8, 0x20, 0xd9, 0x23, 0xee, 0xef]
SEI_MESSAGE_2 = [0x12, 0x67, 0x56, 0xda, 0xef, 0x99, 0x00, 0xbb, 0x6a, 0xc4, 0xd8, 0x10, 0xf9, 0xe3, 0x3e, 0x8f]


def encode_with_sei_msg(gpu_id, dec_file_path, enc_file_path, width, height, fmt, config_params, frame_count=0):
    """
    Encode frames with SEI message insertion into the bitstream using CUDA device buffers as input.

    This function reads image data from a file and loads it to CUDA input buffers using FetchGPUFrame().
    The encoder copies the CUDA buffers and SEI message data and submits them to NVENC hardware for encoding.
    Video memory buffer is allocated to get the NVENC hardware output, which is then copied to host memory
    for file storage.

    Parameters:
        gpu_id (int): Ordinal of GPU to use [Parameter not in use]
        dec_file_path (str): Path to file to be decoded
        enc_file_path (str): Path to output file for encoded frames
        width (int): Width of encoded frame
        height (int): Height of encoded frame
        fmt (str): Surface format string in uppercase (e.g., "NV12")
        config_params (dict): Key-value pairs providing fine-grained control on encoding

    Returns:
        None

    Example:
        >>> encode(0, "input.yuv", "output.h264", 1920, 1080, "NV12", {"codec": "h264"})
        Encode 1080p NV12 raw YUV into elementary bitstream using H.264 codec with SEI messages
    """
    try:
        # Determine SEI type based on codec
        if config_params["codec"] in ["hevc", "h264"]:
            sei_info = {"sei_type": 5}
        elif config_params["codec"] == "av1":
            sei_info = {"sei_type": 6}
        else:
            raise ValueError(f"Unsupported codec: {config_params['codec']}")

        # Create SEI messages list
        sei_messages = [(sei_info, SEI_MESSAGE_1), (sei_info, SEI_MESSAGE_2)]

        with open(dec_file_path, "rb") as decFile, open(enc_file_path, "wb") as encFile:
            # Create encoder object
            config_params["gpu_id"] = gpu_id
            nvenc = nvc.CreateEncoder(width, height, fmt, False, **config_params)
            
            # Create input frame list
            input_frame_list = [AppFrame(width, height, fmt) for _ in range(1, 5)]
            
            # Process frames
            # Calculate total available frames from file size
            file_size = os.path.getsize(dec_file_path)
            available_frames = file_size // input_frame_list[0].frameSize
            
            # Determine frames to process
            frames_to_process = frame_count if frame_count > 0 else available_frames
            frames_to_process = min(frames_to_process, available_frames)
            
            print(f"File contains {available_frames} frames, processing {frames_to_process} frames")
            
            for input_gpu_frame in FetchGPUFrame(
                input_frame_list,
                FetchCPUFrame(decFile, input_frame_list[0].frameSize),
                frames_to_process
            ):
                bitstream = nvenc.Encode(input_gpu_frame, 0, sei_messages)
                encFile.write(bytearray(bitstream))
            
            # Flush encoder queue
            bitstream = nvenc.EndEncode()
            encFile.write(bytearray(bitstream))
        
        print(f"Encoded frames written to {enc_file_path} with SEI messages")

    except nvc.PyNvVCExceptionUnsupported as e:
        print(f"CreateEncoder failure: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    args = parse_sei_encode_args(
        "This sample application illustrates encoding of frames with SEI message insertion."
    )

    print("=" * 60)
    print("Configuration:")
    print(f"Input: {args.raw_file_path}")
    print(f"Output: {args.encoded_file_path}")
    print(f"Size: {args.width}x{args.height}")
    print(f"Format: {args.format}")
    print(f"Codec: {args.codec}")
    print(f"GPU ID: {args.gpu_id}")
    print(f"Frame count: {args.frame_count if args.frame_count > 0 else 'All frames'}")
    print("=" * 60)

    encode_with_sei_msg(
        args.gpu_id,
        args.raw_file_path.as_posix(),
        args.encoded_file_path.as_posix(),
        args.width,
        args.height,
        args.format,
        args.config,
        args.frame_count
    )