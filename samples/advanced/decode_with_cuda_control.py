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
This sample demonstrates advanced video decoding with explicit CUDA resource management.

It shows how to:
1. Initialize and manage CUDA contexts and streams
2. Set up a decoder with custom CUDA resources
3. Handle device memory and data transfers
4. Clean up CUDA resources properly

Key Learning Outcomes:
1. Using explicit CUDA context management for decoder creation. This enables the application to have full control over the CUDA resources.
2. Proper CUDA resource cleanup order: decoder → demuxer → stream → context
3. Switching between device memory (zero-copy) and host memory modes (use_device_memory)
4. Querying hardware capabilities like number of decoder engines


Usage: python decode_with_cuda_control.py -i <input_video_file> -o <output_file> -d <use_device_memory>
Example: python decode_with_cuda_control.py -i input.mp4 -o output.yuv -d 1

Arguments:
  -i: Input video file
  -o: Output raw video file (default: <input_name>.yuv)
  -d: Use device memory (1) or host memory (0) (default: 1)
  -g: GPU ID to use (default: 0)
  -f: Number of frames to decode (optional, default: all frames)
'''

import sys
from pathlib import Path
try:
    import pycuda.driver as cuda
    CudaError = cuda.Error
except ImportError:
    cuda = None
    CudaError = RuntimeError
import PyNvVideoCodec as nvc
from os.path import join, dirname, abspath, splitext

# Add the parent directory to Python path in a way that works from any working directory
current_dir = dirname(abspath(__file__))
parent_dir = dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Import utilities for decoding
from utils.decode_parser import parse_decode_args
from utils.Utils import get_frame_data
from utils.backend_utils import context_stream_kwargs, is_musa_build



def decode(gpu_id, enc_file_path, dec_file_path, use_device_memory, frame_count=None):
    """
    Function to decode media file and write raw frames into an output file.
    Demonstrates explicit CUDA context and stream handling for decoder operations.

    This function demonstrates hardware-accelerated video decoding. Here's how it works:
    1. Creates a demuxer (nv_dmx) that reads the video file and extracts encoded frame packets
    2. Sets up a GPU decoder (nv_dec) with custom CUDA context and stream
    3. The demuxer automatically extracts frame packets as you iterate over it
    4. Each packet is sent to the GPU decoder for hardware-accelerated decoding
    5. The decoder outputs raw YUV frames that can be processed or saved

    Parameters:
        gpu_id (int): Ordinal of GPU to use
        enc_file_path (str): Path to file to be decoded
        dec_file_path (str): Path to output file into which raw frames are stored
        use_device_memory (int): If set to 1, output decoded frame is device pointer wrapped in backend array interface
        frame_count (int, optional): Maximum number of frames to decode. If None, 0, or negative, decode all frames.
    """
    musa_build = is_musa_build(nvc)

    # Validate GPU ID for CUDA. MUSA mode uses default context/stream handles because
    # this sample does not manage an explicit MUSA stream through a Python runtime API.
    if not musa_build:
        if cuda is None:
            raise RuntimeError("CUDA sample support requires pycuda to be installed")
        try:
            cuda.init()
            device_count = cuda.Device.count()
            if gpu_id < 0 or gpu_id >= device_count:
                raise ValueError(f"Invalid GPU ID {gpu_id}. Available GPUs: {device_count}")
        except cuda.Error as e:
            raise RuntimeError(f"CUDA initialization failed: {e}")

    # Normalize frame count
    decode_all = frame_count is None or frame_count <= 0
    if decode_all:
        print("Decoding all available frames")
        frame_count = None

    cuda_ctx = None
    cuda_stream = None
    nv_dmx = None
    nv_dec = None
    frames_decoded = 0

    try:
        if musa_build:
            print(f"Using default MUSA context and stream for GPU {gpu_id}")
        else:
            # Initialize CUDA context and stream
            print(f"Initializing CUDA for GPU {gpu_id}")
            cuda_device = cuda.Device(gpu_id)
            cuda_ctx = cuda_device.retain_primary_context()
            cuda_ctx.push()
            print(f"Created CUDA context for device: {cuda_device.name()}")

            # Create CUDA stream for asynchronous operations
            cuda_stream = cuda.Stream()
            print("Created CUDA stream for asynchronous operations")

        # Create demuxer and get codec information
        nv_dmx = nvc.CreateDemuxer(filename=enc_file_path)
        print(f"Created demuxer for file: {enc_file_path}")
        print(f"Codec: {nv_dmx.GetNvCodecId()}")
        print(f"Chroma Format: {nv_dmx.ChromaFormat()}")
        print(f"Bit Depth: {nv_dmx.BitDepth()}")

        # Get decoder capabilities
        caps = nvc.GetDecoderCaps(
            gpuid=gpu_id,
            codec=nv_dmx.GetNvCodecId(),
            chromaformat=nv_dmx.ChromaFormat(),
            bitdepth=nv_dmx.BitDepth()
        )
        if "num_decoder_engines" in caps:
            print("Number of NVDECs:", caps["num_decoder_engines"])

        context_handle = cuda_ctx.handle if cuda_ctx is not None else 0
        stream_handle = cuda_stream.handle if cuda_stream is not None else 0
        nv_dec = nvc.CreateDecoder(gpuid=gpu_id,
                               codec=nv_dmx.GetNvCodecId(),
                               **context_stream_kwargs(nvc, context_handle, stream_handle),
                               usedevicememory=use_device_memory)
        backend_label = "MUSA" if musa_build else "CUDA"
        print(f"Created decoder with {backend_label} context and stream")
        print("FPS =", nv_dmx.FrameRate())

        # Process frames
        with open(dec_file_path, "wb") as decFile:
            for packet in nv_dmx:
                decoded_frames = nv_dec.Decode(packet)
                for decoded_frame in decoded_frames:
                    if frame_count is not None and frames_decoded >= frame_count:
                        break

                    # Get frame data using Utils helper function
                    frame_data = get_frame_data(decoded_frame, use_device_memory)
                    decFile.write(bytearray(frame_data))
                    frames_decoded += 1

                    if frame_count is not None and frames_decoded >= frame_count:
                        print(f"Successfully decoded requested {frame_count} frames to {dec_file_path}")
                        return

            # If we get here, we've decoded all available frames
            if frame_count is not None and frames_decoded < frame_count:
                print(f"Warning: Video ended before reaching requested frame count. Requested: {frame_count}, Decoded: {frames_decoded}")
                print(f"Decoded frames written to {dec_file_path}")
            else:
                print(f"Successfully decoded all {frames_decoded} frames to {dec_file_path}")

    except nvc.PyNvVCExceptionUnsupported as e:
        print(f"Operation or configuration not supported: {e}")
        raise
    except CudaError as e:
        print(f"CUDA error (context/stream/memory): {e}")
        raise
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise
    finally:
        # Cleanup resources in reverse order of creation
        if nv_dec is not None:
            del nv_dec
        if nv_dmx is not None:
            del nv_dmx
        if cuda_stream is not None:
            cuda_stream.synchronize()
            del cuda_stream
        if cuda_ctx is not None:
            cuda_ctx.pop()
            del cuda_ctx

if __name__ == "__main__":
    args = parse_decode_args(
        "Advanced video decoding with explicit CUDA context and stream handling. "
        "Demonstrates fine-grained control over CUDA resources and synchronization."
    )
    print("=" * 60)
    print("Configuration:")
    print(f"Input: {args.encoded_file_path}")
    print(f"Output: {args.raw_file_path}")
    print(f"GPU ID: {args.gpu_id}")
    print(f"Use Device Memory: {args.use_device_memory}")
    print(f"Frame Count: {args.frame_count if args.frame_count else 'All frames'}")
    print("=" * 60)

    decode(
        gpu_id=args.gpu_id,
        enc_file_path=args.encoded_file_path,
        dec_file_path=args.raw_file_path,
        use_device_memory=args.use_device_memory,
        frame_count=args.frame_count,
    )
