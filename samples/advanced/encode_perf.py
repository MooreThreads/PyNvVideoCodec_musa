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
This sample demonstrates advanced parallel video encoding using multiple threads or processes.
It shows how to:
1. Maximize GPU utilization using multiple encoder instances
2. Measure encoding performance (FPS) accurately for different modes
3. Scale encoding across available NVENC engines
4. Use either threading or multiprocessing for parallelization
5. Manage shared resources and cleanup
6. Track and report performance metrics

The sample implements two parallel execution modes:
- Thread Mode:
  * Multiple encoders in the same process
  * Shared memory access
  * Lower overhead, simpler synchronization
  * Best for CPU-bound workloads

- Process Mode:
  * Multiple encoders in separate processes
  * IPC memory sharing
  * Better isolation and stability
  * Best for GPU-bound workloads


Usage:
    python encode_perf.py -m <mode> -i <input_file> -s <size> [options]

Example:
    python encode_perf.py -m threads -i input.yuv -s 1920x1080 -n 4

Arguments:
    -m: Execution mode ('threads' or 'processes')
    -i: Raw input video file
    -s: Frame size (e.g., 1920x1080)
    -if: Input format (default: NV12)
    -c: Codec (H264, HEVC, AV1)
    -n: Number of workers (default: 1)
    -f: Frames per worker (default: all)
    -g: GPU ID (default: 0)
    -json: Encoder config file

Note: This performance testing app does not write output files.
      It only measures encoding throughput.

Note: For optimal performance:
- Use thread mode for smaller workloads or when CPU is the bottleneck
- Use process mode for larger workloads or when GPU is the bottleneck
- Adjust worker count based on available CPU cores and GPU resources
'''

import gc
import sys
import atexit
import os
import time
import queue
import threading
import multiprocessing
from multiprocessing import Process
try:
    import pycuda.driver as cuda
except ImportError:
    cuda = None
import PyNvVideoCodec as nvc
from os.path import dirname, abspath


# Add the parent directory to Python path in a way that works from any working directory
current_dir = dirname(abspath(__file__))
parent_dir = dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Import utilities for encoding
from utils.Utils import AppFramePerf
from utils.backend_utils import context_stream_kwargs, is_musa_build
from utils.encode_parser import parse_perf_args, PERF_MAX_FRAMES
from utils.frame_utils import get_frame_size, create_memory_map, allocate_device_memory
from utils.encode_parallel_utils import (
    print_performance_summary,
    encode_thread_worker,
    encode_process_worker
)


# Global variables to track resources for cleanup
g_devicedata = None
g_mmap = None
g_context = None


def cleanup_resources():
    """Clean up global resources including memory map, GPU memory, and CUDA context."""
    global g_devicedata, g_mmap, g_context

    gc.collect()

    if g_mmap:
        try:
            g_mmap.close()
            g_mmap = None
        except:
            pass

    if g_devicedata:
        try:
            g_devicedata.free()
            g_devicedata = None
        except:
            pass

    if g_context:
        try:
            g_context.detach()
            g_context = None
        except:
            pass


atexit.register(cleanup_resources)


def run_threaded_encode(args):
    """Run encoding with multiple threads using shared device memory."""
    musa_build = is_musa_build(nvc)
    print(f"Initializing {args.num_workers} encode thread{'s' if args.num_workers > 1 else ''}")

    # Calculate total frames and show warning if needed
    framesize = get_frame_size(args.width, args.height, args.format)
    file_size = os.path.getsize(args.raw_file_path)
    available_frames = file_size // framesize

    if available_frames > PERF_MAX_FRAMES and args.frame_count == 0:
        print(f"\nWarning: File contains {available_frames} frames. Limiting to {PERF_MAX_FRAMES} frames for performance testing.")
    elif args.frame_count > PERF_MAX_FRAMES:
        print(f"\nWarning: Requested {args.frame_count} frames. Limiting to {PERF_MAX_FRAMES} frames for performance testing.")

    global g_devicedata, g_mmap, g_context

    try:
        if not musa_build:
            if cuda is None:
                raise RuntimeError("CUDA sample support requires pycuda to be installed")
            # Initialize CUDA
            cuda.init()
            cuda_device = cuda.Device(args.gpu_id)
            g_context = cuda_device.make_context()
            shared_stream = cuda.Stream()
            context_handle = g_context.handle
            stream_handle = shared_stream.handle
        else:
            print(f"Using default MUSA context and stream for GPU {args.gpu_id}")
            context_handle = 0
            stream_handle = 0

        # Open input file and prepare data
        with open(args.raw_file_path, "rb") as input_file:
            framesize = get_frame_size(args.width, args.height, args.format)
            g_mmap = create_memory_map(input_file)

            # Calculate frames to process
            frames_to_process = args.frame_count if args.frame_count > 0 else available_frames
            frames_to_process = min(frames_to_process, available_frames, PERF_MAX_FRAMES)
            bytes_to_read = frames_to_process * framesize

            print(f"File contains {available_frames} frames, processing {frames_to_process} frames")

            # Read and copy data to GPU
            hostdata = g_mmap.read(bytes_to_read)
            g_devicedata = allocate_device_memory(hostdata)

            # Create encoders
            encoders = []
            for _ in range(args.num_workers):
                config = args.config.copy()
                encoder = nvc.CreateEncoder(
                    args.width, args.height, args.format, False,
                    **context_stream_kwargs(nvc, context_handle, stream_handle),
                    **config
                )
                encoders.append(encoder)

            # Run encoding threads
            result_queue = queue.Queue()
            begin = time.perf_counter()

            threads = []
            for i in range(args.num_workers):
                t = threading.Thread(
                    target=encode_thread_worker,
                    args=(
                        i, args.raw_file_path, encoders[i], g_devicedata,
                        framesize, args.width, args.height, args.format,
                        args.frame_count, result_queue
                    )
                )
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            duration = time.perf_counter() - begin

            # Collect and print results
            total_frames = sum(result_queue.get() for _ in range(args.num_workers))
            print_performance_summary("threads", args.num_workers, total_frames, duration)

            # Cleanup
            for encoder in encoders:
                del encoder
            encoders.clear()

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if g_context is not None:
            g_context.pop()


def run_multiprocess_encode(args):
    """Run encoding with multiple processes using IPC memory sharing."""
    if not hasattr(cuda, "mem_get_ipc_handle"):
        raise RuntimeError(
            "PyCUDA does not provide mem_get_ipc_handle; install the MUSA-capable PyCUDA fork for MUSA process mode"
        )

    print(f"Initializing {args.num_workers} encode process{'es' if args.num_workers > 1 else ''}")

    # Calculate total frames and show warning if needed
    framesize = get_frame_size(args.width, args.height, args.format)
    file_size = os.path.getsize(args.raw_file_path)
    available_frames = file_size // framesize

    if available_frames > PERF_MAX_FRAMES and args.frame_count == 0:
        print(f"\nWarning: File contains {available_frames} frames. Limiting to {PERF_MAX_FRAMES} frames for performance testing.")
    elif args.frame_count > PERF_MAX_FRAMES:
        print(f"\nWarning: Requested {args.frame_count} frames. Limiting to {PERF_MAX_FRAMES} frames for performance testing.")

    framesize = get_frame_size(args.width, args.height, args.format)

    with open(args.raw_file_path, "rb") as input_file:
        # Calculate frames to process
        file_size = os.path.getsize(args.raw_file_path)
        total_frames = file_size // framesize
        frames_to_process = args.frame_count if args.frame_count > 0 else total_frames
        frames_to_process = min(frames_to_process, total_frames, PERF_MAX_FRAMES)
        bytes_to_read = frames_to_process * framesize

        print(f"File contains {total_frames} frames, processing {frames_to_process} frames")

        # Prepare shared memory
        m = create_memory_map(input_file)
        hostdata = m.read(bytes_to_read)
        devicedata = allocate_device_memory(hostdata)
        devptrhandle = cuda.mem_get_ipc_handle(devicedata)

        # Run encoding processes
        result_queue = multiprocessing.Queue()
        begin = time.perf_counter()

        processes = []
        for i in range(args.num_workers):
            config = args.config.copy()
            p = Process(
                target=encode_process_worker,
                args=(
                    i, args.raw_file_path, args.width, args.height,
                    args.format, devptrhandle, framesize, config,
                    frames_to_process, result_queue
                )
            )
            processes.append(p)
            p.start()

        for p in processes:
            p.join()

        duration = time.perf_counter() - begin

        # Collect and print results
        total_frames = sum(result_queue.get() for _ in range(args.num_workers))
        print_performance_summary("processes", args.num_workers, total_frames, duration)

        # Cleanup
        devicedata.free()
        m.close()

    print("All encoding processes completed")


if __name__ == "__main__":
    args = parse_perf_args(
        "Parallel video encoding application supporting both multithreading and multiprocessing for performance testing."
    )

    # Set multiprocessing start method for compatibility
    if args.mode == "process":
        multiprocessing.set_start_method('spawn')

    try:
        if args.mode == "thread":
            run_threaded_encode(args)
        else:  # processes
            run_multiprocess_encode(args)
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        cleanup_resources()
