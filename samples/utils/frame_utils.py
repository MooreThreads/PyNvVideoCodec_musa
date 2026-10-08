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
Helper module for frame and memory management in video encoding/decoding.
"""

import mmap
import sys
try:
    import pycuda.driver as cuda
except ImportError:
    cuda = None

def get_frame_size(width: int, height: int, surface_format: str) -> int:
    """
    Calculate the size of a frame in bytes based on its dimensions and format.

    Parameters:
        width (int): Width of the frame
        height (int): Height of the frame
        surface_format (str): Format of the surface (e.g., "NV12", "ARGB", "YUV444")

    Returns:
        int: Size of the frame in bytes
    """
    if surface_format in ("ARGB", "ABGR"):
        return width * height * 4
    elif surface_format == "YUV444":
        return width * height * 3
    elif surface_format == "YUV420":
        return int(width * height * 3 / 2)
    elif surface_format == "P010":
        return int(width * height * 3 / 2 * 2)
    elif surface_format == "YUV444_16BIT":
        return int(width * height * 3 * 2)
    elif surface_format == "NV16":
        return width * height * 2
    elif surface_format == "P210":
        return width * height * 2 * 2
    else:  # Default NV12
        return int(width * height * 3 / 2)

def create_memory_map(file_handle, access_read=True) -> mmap.mmap:
    """
    Create a memory map for a file with cross-platform support.

    Parameters:
        file_handle: File object to memory map
        access_read: If True, create read-only mapping, else read-write

    Returns:
        mmap.mmap: Memory mapped file object
    """
    if sys.platform == 'win32':
        return mmap.mmap(file_handle.fileno(), 0, access=mmap.ACCESS_READ if access_read else mmap.ACCESS_WRITE)
    else:
        return mmap.mmap(file_handle.fileno(), 0, prot=mmap.PROT_READ if access_read else mmap.PROT_WRITE)

def allocate_device_memory(host_data):
    """
    Allocate CUDA device memory and copy host data.

    Parameters:
        host_data: Data to copy to device

    Returns:
        cuda.DeviceAllocation: Allocated device memory with copied data
    """
    if cuda is None:
        raise RuntimeError("CUDA memory allocation requires pycuda to be installed")
    device_data = cuda.mem_alloc(len(host_data))
    cuda.memcpy_htod(device_data, host_data)
    return device_data
