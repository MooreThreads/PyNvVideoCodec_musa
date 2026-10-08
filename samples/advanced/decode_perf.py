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
This sample demonstrates how to measure video decoding performance by utilizing multiple NVDEC engines in parallel.

It shows how to:
1. Maximize GPU utilization using multiple decoder instances
2. Measure decoding performance (FPS) accurately for different modes
3. Scale decoding across available NVDEC engines
4. Use either threading or multiprocessing for parallelization
5. Track and report performance metrics

The sample implements two parallel execution modes:
Thread Mode:
- Better for: Higher performance (lower overhead), shared memory access (decoder instances can share the same GPU memory)
- Ideal when: Running on same GPU, memory constraints exist
- Benefits: Faster initialization, lower memory footprint, cuda context is shared between decoder instances
- Note: Python GIL is not a bottleneck as decoder operations are GIL-free

Process Mode:
- Better for: Complete isolation between decoder instances (each decoder instance has its own GPU memory)
- Ideal when: Running on multiple GPUs, need memory isolation
- Benefits: Better fault isolation, independent memory management
- Tradeoff: Higher memory usage, longer initialization time, cuda context is not shared between decoder instances

Usage: python decode_perf.py -i <input_file> -n <num_instances> -m <mode>
Example: python decode_perf.py -i input.mp4 -n 4 -m thread

Arguments:
  -i: Input video file
  -n: Number of parallel instances (default: 1)
  -m: Execution mode: 'thread' or 'process' (default: thread)
  -d: Use device memory (1) or host memory (0) (default: 1)
  -g: GPU ID to use (default: 0)
  -f: Number of frames to decode per instance (optional)

Note: This performance testing app does not write output files.
      It only measures decoding throughput.
'''

import sys
import os
import time
import threading
import multiprocessing
from pathlib import Path
import PyNvVideoCodec as nvc
from os.path import join, dirname, abspath

# Set multiprocessing start method at the very beginning
# 'spawn' is required for CUDA operations and works consistently across platforms
if __name__ == '__main__':
    multiprocessing.set_start_method('spawn')

# Add the parent directory to Python path in a way that works from any working directory
current_dir = dirname(abspath(__file__))
parent_dir = dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Import utilities for decoding
from utils.decode_parser import parse_multi_instance_args
from utils.backend_utils import set_decoder_session_count


# Global variables for tracking performance metrics in threading mode
total_fps = 0
num_frames = 0
perf_lock = threading.Lock()

def decode_thread(gpu_id, enc_file_path, frame_count=None):
    """
    Function to decode media file and measure performance in a thread.

    Parameters:
        gpu_id (int): Ordinal of GPU to use
        enc_file_path (str): Path to file to be decoded
        frame_count (int, optional): Maximum number of frames to decode
    """
    global total_fps, num_frames

    try:
        # Normalize frame count
        decode_all = frame_count is None or frame_count <= 0
        if decode_all:
            print(f"Thread {threading.current_thread().name}: Decoding all available frames")
            frame_count = None

        nv_dmx = nvc.CreateDemuxer(filename=enc_file_path)
        nv_dec = nvc.CreateDecoder(
            gpuid=gpu_id,
            codec=nv_dmx.GetNvCodecId(),
            usedevicememory=True,
            bWaitForSessionWarmUp=True
        )

        start = time.perf_counter()
        num_decoded_frames = 0

        for packet in nv_dmx:
            for _ in nv_dec.Decode(packet):
                num_decoded_frames += 1
                if frame_count is not None and num_decoded_frames >= frame_count:
                    print(f"Thread {threading.current_thread().name}: Successfully decoded requested {frame_count} frames")
                    break

            if frame_count is not None and num_decoded_frames >= frame_count:
                break

        # If we get here, we've decoded all available frames
        if frame_count is not None and num_decoded_frames < frame_count:
            print(f"Thread {threading.current_thread().name}: Warning: Video ended before reaching requested frame count. Requested: {frame_count}, Decoded: {num_decoded_frames}")
        else:
            print(f"Thread {threading.current_thread().name}: Successfully decoded all {num_decoded_frames} frames")

        # Calculate accurate elapsed time by subtracting initialization time
        elapsed_time = time.perf_counter() - start
        init_time = nv_dec.GetSessionInitTime() / 1000.0  # Convert to seconds
        elapsed_time -= init_time

        fps = num_decoded_frames / elapsed_time
        print(f"Thread {threading.current_thread().name}: {num_decoded_frames} frames in {elapsed_time:.2f}s ({fps:.2f} FPS)")

        # Update performance metrics with thread-safe operation
        with perf_lock:
            global total_fps, num_frames
            total_fps += fps
            num_frames += num_decoded_frames

    except Exception as e:
        print(f"Thread {threading.current_thread().name} error: {e}")

def decode_process(gpu_id, enc_file_path, frame_count=None, result_queue=None):
    """
    Function to decode media file and measure performance in a separate process.

    Parameters:
        gpu_id (int): Ordinal of GPU to use
        enc_file_path (str): Path to file to be decoded
        frame_count (int, optional): Maximum number of frames to decode
        result_queue (Queue): Queue to store performance results
    """
    try:
        # Normalize frame count
        decode_all = frame_count is None or frame_count <= 0
        if decode_all:
            print(f"Process {multiprocessing.current_process().name}: Decoding all available frames")
            frame_count = None

        nv_dmx = nvc.CreateDemuxer(filename=enc_file_path)
        nv_dec = nvc.CreateDecoder(
            gpuid=gpu_id,
            codec=nv_dmx.GetNvCodecId(),
            usedevicememory=True,
        )

        start = time.perf_counter()
        num_decoded_frames = 0

        for packet in nv_dmx:
            for _ in nv_dec.Decode(packet):
                num_decoded_frames += 1
                if frame_count is not None and num_decoded_frames >= frame_count:
                    print(f"Process {multiprocessing.current_process().name}: Successfully decoded requested {frame_count} frames")
                    break

            if frame_count is not None and num_decoded_frames >= frame_count:
                break

        # If we get here, we've decoded all available frames
        if frame_count is not None and num_decoded_frames < frame_count:
            print(f"Process {multiprocessing.current_process().name}: Warning: Video ended before reaching requested frame count. Requested: {frame_count}, Decoded: {num_decoded_frames}")
        else:
            print(f"Process {multiprocessing.current_process().name}: Successfully decoded all {num_decoded_frames} frames")

        elapsed_time = time.perf_counter() - start
        fps = num_decoded_frames / elapsed_time
        print(f"Process {multiprocessing.current_process().name}: {num_decoded_frames} frames in {elapsed_time:.2f}s ({fps:.2f} FPS)")

        # Send results back through queue
        if result_queue:
            result_queue.put((fps, num_decoded_frames))

    except Exception as e:
        print(f"Process {multiprocessing.current_process().name} error: {e}")
        if result_queue:
            result_queue.put((0, 0))  # Send zero metrics on error

def run_parallel_decode(mode, num_instances, gpu_id, enc_file_path, frame_count=None):
    """
    Run parallel video decoding using either threads or processes.

    Parameters:
        mode (str): 'thread' or 'process' to specify parallel execution mode
        num_instances (int): Number of parallel decode instances to run
        gpu_id (int): Ordinal of GPU to use
        enc_file_path (str): Path to file to be decoded
        frame_count (int, optional): Maximum number of frames to decode per instance
    """
    global total_fps, num_frames
    total_fps = 0
    num_frames = 0

    start_time = time.perf_counter()

    if mode == 'thread':
        # Threading mode
        threads = []
        set_decoder_session_count(nvc, num_instances)

        for i in range(num_instances):
            t = threading.Thread(
                target=decode_thread,
                args=(gpu_id, enc_file_path, frame_count)
            )
            print(f"Starting decode thread {i+1}/{num_instances}")
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        # Performance metrics are collected via global variables

    else:  # mode == 'process'
        # Multiprocessing mode
        processes = []
        result_queue = multiprocessing.Queue()

        for i in range(num_instances):
            p = multiprocessing.Process(
                target=decode_process,
                args=(gpu_id, enc_file_path, frame_count, result_queue)
            )
            print(f"Starting decode process {i+1}/{num_instances}")
            p.start()
            processes.append(p)

        for p in processes:
            p.join()

        # Collect results from queue
        while not result_queue.empty():
            fps, frames = result_queue.get()
            total_fps += fps
            num_frames += frames

    total_time = time.perf_counter() - start_time

    # Print performance summary
    print("\n=== Performance Summary ===")
    print(f"Mode: {mode.capitalize()}")
    print(f"Number of instances: {num_instances}")
    print(f"Total frames decoded: {num_frames}")
    print(f"Total FPS: {total_fps:.2f}")
    print(f"Average FPS per instance: {total_fps/num_instances:.2f}")
    print(f"Total wall time: {total_time:.2f}s")
    print("========================\n")

if __name__ == "__main__":

    args = parse_multi_instance_args()

    print("=" * 60)
    print("Configuration:")
    print(f"Input: {args.encoded_file_path}")
    print(f"GPU ID: {args.gpu_id}")
    print(f"Mode: {args.mode.upper()}")
    print(f"Number of Instances: {args.num_instances}")
    print(f"Frame Count: {args.frame_count if args.frame_count else 'All frames'}")
    print("=" * 60)

    run_parallel_decode(
        mode=args.mode,
        num_instances=args.num_instances,
        gpu_id=args.gpu_id,
        enc_file_path=args.encoded_file_path,
        frame_count=args.frame_count,
    )
