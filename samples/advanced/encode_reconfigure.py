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
This sample demonstrates dynamic encoder reconfiguration for bitrate control.
It shows how to:
1. Change encoder parameters at runtime
2. Modify bitrate without resetting the encoder
3. Handle VBV (Video Buffer Verifier) parameters
4. Maintain encoding quality during changes

Note: Bitrate changes occur every 100 frames:
- Frame 0: Original bitrate
- Frame 100: Half bitrate
- Frame 200: Original bitrate
- And so on...

Usage:
    python encode_reconfigure.py -i <input_file> -s <size> [options]

Example:
    python encode_reconfigure.py -i input.yuv -s 1920x1080

Arguments:
    -i: Raw input video file
    -s: Frame size (e.g., 1920x1080)
    -if: Input format (default: NV12)
    -c: Codec (H264, HEVC, AV1)
    -f: Number of frames (default: all)
    -g: GPU ID (default: 0)
    -json: Encoder config file


'''

import PyNvVideoCodec as nvc
import numpy as np
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

from utils.encode_parser import parse_reconfigure_encode_args


# Constants
BITRATE_CHANGE_INTERVAL = 100
BITRATE_REDUCTION_FACTOR = 2


def encode(gpu_id, dec_file_path, enc_file_path, width, height, fmt, config_params, frame_count=0):
    """
    Encode video with dynamic bitrate reconfiguration.

    This function demonstrates bitrate change at runtime without the need to reset the encoder session.
    The application reduces the bitrate by half and then restores it to the original value after
    every 100 frames.

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
        Encode 1080p NV12 raw YUV into elementary bitstream using H.264 codec
    """
    try:
        with open(dec_file_path, "rb") as decFile, open(enc_file_path, "wb") as encFile:
            # Create encoder object
            config_params["gpu_id"] = gpu_id
            
            if "tuning_info" in config_params:
                tuning_info_val = config_params['tuning_info']
                if tuning_info_val == "low_latency":
                    config_params['bf'] = 0
            
            nvenc = nvc.CreateEncoder(width, height, fmt, False, **config_params)
            # Create input frame list
            input_frame_list = [AppFrame(width, height, fmt) for _ in range(1, 5)]
            
            # Get initial encoder parameters
            reconf_params = nvenc.GetEncodeReconfigureParams()
            original_avgbitrate = reconf_params.averageBitrate
            if "vbvbufsize" in config_params:
                original_vbvbuffersize = config_params['vbvbufsize']
            else:
                original_vbvbuffersize = int(original_avgbitrate * reconf_params.frameRateDen / reconf_params.frameRateNum)
            
            original_vbvinitdelay = original_vbvbuffersize
            
            
            # Process frames
            # Calculate total available frames from file size
            file_size = os.path.getsize(dec_file_path)
            available_frames = file_size // input_frame_list[0].frameSize
            
            # Determine frames to process
            frames_to_process = frame_count if frame_count > 0 else available_frames
            frames_to_process = min(frames_to_process, available_frames)
            
            print(f"File contains {available_frames} frames, processing {frames_to_process} frames")
            
            for i, input_gpu_frame in enumerate(
                FetchGPUFrame(
                    input_frame_list,
                    FetchCPUFrame(decFile, input_frame_list[0].frameSize),
                    frames_to_process
                )
            ):
                # Reconfigure bitrate every 100 frames
                if i % BITRATE_CHANGE_INTERVAL == 0:
                    if i % (BITRATE_CHANGE_INTERVAL * 2) != 0:
                        # Reduce bitrate by half
                        reconf_params.averageBitrate = int(original_avgbitrate / BITRATE_REDUCTION_FACTOR)
                        reconf_params.vbvBufferSize = int(original_vbvbuffersize / BITRATE_REDUCTION_FACTOR)
                        reconf_params.vbvInitialDelay = int(original_vbvinitdelay / BITRATE_REDUCTION_FACTOR)
                    else:
                        # Restore original bitrate
                        reconf_params.averageBitrate = original_avgbitrate
                        reconf_params.vbvBufferSize = original_vbvbuffersize
                        reconf_params.vbvInitialDelay = original_vbvinitdelay
                    
                    nvenc.Reconfigure(reconf_params)
                
                # Encode frame
                bitstream = nvenc.Encode(input_gpu_frame)
                encFile.write(bytearray(bitstream))
            
            # Flush encoder queue
            bitstream = nvenc.EndEncode()
            encFile.write(bytearray(bitstream))
            print(f"Completed encoding {frames_to_process} frames using CPU buffers")
            print(f"Output file: {enc_file_path}")
            
    except nvc.PyNvVCExceptionUnsupported as e:
        print(f"CreateEncoder failure: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    args = parse_reconfigure_encode_args(
        "This sample application demonstrates bitrate change at runtime without resetting the encoder session."
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

    encode(
        args.gpu_id,
        args.raw_file_path.as_posix(),
        args.encoded_file_path.as_posix(),
        args.width,
        args.height,
        args.format,
        args.config,
        args.frame_count
    )
