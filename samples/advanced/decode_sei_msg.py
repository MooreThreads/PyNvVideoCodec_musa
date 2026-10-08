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
This sample demonstrates how to extract and parse Supplemental Enhancement Information (SEI) from video streams.

It shows how to:
1. Access SEI messages from decoded frames and write them to a file
2. Parse different SEI message types


SEI messages are additional data embedded in video streams that provide supplementary information:
- HDR/Display Metadata: Color volume, light levels, and transfer characteristics for HDR content
- Timecode Data: Frame timing and sequence information
- Custom Metadata: User-defined data for application-specific needs

Common Use Cases:
- Video Playback: HDR display configuration and color management
- Content Creation: Frame accurate editing and post-processing
- Broadcast: Timing synchronization and content identification
- Custom Applications: Embedding application-specific metadata in the video stream


Usage: python decode_sei_msg.py -i <input_file> -s <sei_file>
Example: python decode_sei_msg.py -i input.mp4 -s sei_data.bin

Arguments:
  -i: Input video file
  -s: Output SEI message file (default: sei_message.bin).
  -st: Output SEI type message file (default: sei_type_message.bin)
  -d: Use device memory (1) or host memory (0) (default: 1)
  -g: GPU ID to use (default: 0)
'''

import sys
import numpy as np
import pickle
import ctypes
import argparse
try:
    import pycuda.driver as cuda
except ImportError:
    cuda = None
import PyNvVideoCodec as nvc
from os.path import join, dirname, abspath

# Add the parent directory to Python path in a way that works from any working directory
current_dir = dirname(abspath(__file__))
parent_dir = dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from utils.decode_parser import parse_sei_args
from utils.backend_utils import context_stream_kwargs, is_mpeg2_codec, is_musa_build

from utils.sei_message_parser import (
    TIMECODE, TIMECODEMPEG2, SEICONTENTLIGHTLEVELINFO,
    SEIMASTERINGDISPLAYINFO, SEIALTERNATIVETRANSFERCHARACTERISTICS
)

def extract_sei_messages(gpu_id, enc_file_path, sei_file_path, sei_type_file_path, use_device_memory):
    """
    Function to extract SEI messages from a video file.

    This function decodes a video file and extracts SEI messages, producing three output files:
    1. sei_message.bin - Raw binary SEI messages
    2. sei_type_message.bin - Pickled SEI type information

    Parameters:
        gpu_id (int): Ordinal of GPU to use
        enc_file_path (str): Path to file to be decoded
        sei_file_path (str): Path to output file for SEI messages. Sei type message is written to sei_type_message.bin
        sei_type_file_path (str): Path to output file for SEI type messages.
        use_device_memory (int): If set to 1, output decoded frame is device pointer wrapped in backend array interface

    Returns:
        None
    """
    musa_build = is_musa_build(nvc)
    cuda_ctx = None
    cuda_stream = None

    # Open files for storing SEI data
    file_message = open(sei_file_path, "wb")
    file_type_message = open(sei_type_file_path, "wb")

    try:
        if musa_build:
            print(f"Using default MUSA context and stream for GPU {gpu_id}")
        else:
            if cuda is None:
                raise RuntimeError("CUDA sample support requires pycuda to be installed")
            cuda.init()
            device_id = gpu_id
            cuda_device = cuda.Device(device_id)  # pyright: ignore[reportAttributeAccessIssue]
            cuda_ctx = cuda_device.retain_primary_context()
            cuda_ctx.push()
            cuda_stream = cuda.Stream()

        nv_dmx = nvc.CreateDemuxer(filename=enc_file_path)

        context_handle = cuda_ctx.handle if cuda_ctx is not None else 0
        stream_handle = cuda_stream.handle if cuda_stream is not None else 0
        nv_dec = nvc.CreateDecoder(
            gpuid=gpu_id,
            codec=nv_dmx.GetNvCodecId(),
            **context_stream_kwargs(nvc, context_handle, stream_handle),
            usedevicememory=use_device_memory,
            enableSEIMessage=1
        )

        sei_message_found = False
        print(f"FPS = {nv_dmx.FrameRate()}")


        for packet in nv_dmx:
            for decoded_frame in nv_dec.Decode(packet):

                    # Process SEI messages
                    seiMessage = decoded_frame.getSEIMessage()
                    if seiMessage:
                        sei_message_found = True
                        for sei_info, sei_message in seiMessage:
                            sei_type = sei_info["sei_type"]
                            sei_uncompressed = sei_info["sei_uncompressed"]

                            if sei_uncompressed == 1:
                                buffer = (ctypes.c_ubyte * len(sei_message))(*sei_message)
                                sei_struct = None

                                # Handle different SEI message types
                                if sei_type in (nvc.SEI_TYPE.TIME_CODE_H264, nvc.SEI_TYPE.TIME_CODE):
                                    sei_struct = ctypes.cast(
                                        buffer,
                                        ctypes.POINTER(TIMECODEMPEG2 if is_mpeg2_codec(nvc, nv_dmx.GetNvCodecId()) else TIMECODE)
                                    ).contents
                                elif sei_type == nvc.SEI_TYPE.MASTERING_DISPLAY_COLOR_VOLUME:
                                    sei_struct = ctypes.cast(buffer, ctypes.POINTER(SEIMASTERINGDISPLAYINFO)).contents
                                elif sei_type == nvc.SEI_TYPE.CONTENT_LIGHT_LEVEL_INFO:
                                    sei_struct = ctypes.cast(buffer, ctypes.POINTER(SEICONTENTLIGHTLEVELINFO)).contents
                                elif sei_type == nvc.SEI_TYPE.ALTERNATIVE_TRANSFER_CHARACTERISTICS:
                                    sei_struct = ctypes.cast(buffer, ctypes.POINTER(SEIALTERNATIVETRANSFERCHARACTERISTICS)).contents


                            file_message.write(bytearray(sei_message))
                        pickle.dump(seiMessage, file_type_message)

        if sei_message_found:
            print(f"SEI message written to:")
            print(f"  Binary data: {sei_file_path}")
            print(f"  Type info: {sei_type_file_path}")
        else:
            print("No SEI message found")

    except nvc.PyNvVCExceptionUnsupported as e:
        print(f"CreateDecoder failure: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        file_message.close()
        file_type_message.close()
        if cuda_ctx is not None:
            cuda_ctx.pop()

if __name__ == "__main__":
    args = parse_sei_args(
        "This sample application demonstrates extracting SEI messages from video files."
    )

    print("=" * 60)
    print("Configuration:")
    print(f"Input: {args.encoded_file_path}")
    print(f"SEI Output: {args.sei_file_path}")
    print(f"SEI Type Output: {args.sei_type_file_path}")
    print(f"GPU ID: {args.gpu_id}")
    print(f"Use Device Memory: {args.use_device_memory}")
    print("=" * 60)

    extract_sei_messages(
        args.gpu_id,
        args.encoded_file_path,
        args.sei_file_path,
        args.sei_type_file_path,
        args.use_device_memory
    )
