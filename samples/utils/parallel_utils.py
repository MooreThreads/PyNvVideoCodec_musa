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
Helper module for parallel processing in video encoding/decoding.
"""

import os
import time
import threading
import multiprocessing
from typing import Callable, Any, Dict, Union
import pycuda.driver as cuda
import PyNvVideoCodec as nvc
from Utils import AppFramePerf
from .frame_utils import get_frame_size
from .encode_parser import PERF_MAX_FRAMES

def print_performance_summary(mode: str, num_workers: int, total_frames: int, duration: float) -> None:
    """Print performance statistics for parallel encoding/decoding."""
    print(f"\n--- {mode.capitalize()} Performance Summary ---")
    print(f"Number of {mode}: {num_workers}")
    print(f"Total frames processed: {total_frames}")
    if duration > 0:
        fps = total_frames / duration
        print(f"Duration: {duration:.2f} seconds")
        print(f"Total FPS: {fps:.2f}")
        print(f"Average FPS per {mode[:-1]}: {fps / num_workers:.2f}")

def encode_thread_worker(
    thread_id: int,
    input_file: str,
    encoder: nvc.PyNvEncoder,
    device_data: cuda.DeviceAllocation,
    frame_size: int,
    width: int,
    height: int,
    fmt: str,
    frame_count: int,
    result_queue: Union[multiprocessing.Queue, 'queue.Queue']
) -> None:
    """Worker function for threaded encoding."""
    try:
        worker_name = f"Thread-{thread_id + 1}"  # 1-based indexing
        print(f"Starting encode worker {worker_name}")
        
        # Calculate frames to process
        file_size = os.path.getsize(input_file)
        available_frames = file_size // frame_size
        
        # Determine how many frames to encode
        frames_to_process = min(frame_count or available_frames, available_frames, PERF_MAX_FRAMES)
        
        # Encode frames
        frames_encoded = 0
        for i in range(frames_to_process):
            input_gpu_frame = AppFramePerf(width, height, fmt, device_data, i)
            encoder.Encode(input_gpu_frame)
            frames_encoded += 1
        
        # Flush encoder
        encoder.EndEncode()
        print(f"Worker {worker_name} completed encoding {frames_encoded} frames")
        result_queue.put(frames_encoded)
        
    except Exception as e:
        print(f"Worker {worker_name}: An unexpected error occurred: {e}")
        result_queue.put(0)

def encode_process_worker(
    process_id: int,
    input_file: str,
    width: int,
    height: int,
    fmt: str,
    ipc_handle: Any,
    frame_size: int,
    config: Dict[str, Any],
    frame_count: int,
    result_queue: multiprocessing.Queue
) -> None:
    """Worker function for multiprocess encoding."""
    try:
        worker_name = f"Process-{process_id + 1}"  # 1-based indexing
        print(f"Starting encode worker {worker_name}")
        
        # Create encoder
        encoder = nvc.CreateEncoder(width, height, fmt, False, **config)
        
        # Get device data from IPC handle
        device_data = cuda.IPCMemoryHandle(ipc_handle)
        
        # Calculate frames to process
        file_size = os.path.getsize(input_file)
        available_frames = file_size // frame_size
        
        # Determine how many frames to encode
        frames_to_process = min(frame_count or available_frames, available_frames, PERF_MAX_FRAMES)
        
        # Encode frames
        frames_encoded = 0
        for i in range(frames_to_process):
            input_gpu_frame = AppFramePerf(width, height, fmt, device_data, i)
            encoder.Encode(input_gpu_frame)
            frames_encoded += 1
        
        # Flush encoder
        encoder.EndEncode()
        print(f"Worker {worker_name} completed encoding {frames_encoded} frames")
        result_queue.put(frames_encoded)
        
    except Exception as e:
        print(f"Worker {worker_name}: An unexpected error occurred: {e}")
        result_queue.put(0)
