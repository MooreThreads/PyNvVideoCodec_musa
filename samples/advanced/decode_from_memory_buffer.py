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
This sample demonstrates buffer-based video decoding using memory chunks.

This approach is useful when video data comes from memory buffers
rather than direct file access (e.g., network streams, memory-mapped files). This saves file I/O overhead.

It shows how to:
1. Create a custom data feeder for memory-based video input
2. Set up a demuxer that reads from memory buffers
3. Process video data without direct file I/O
4. Handle streaming data in chunks

Key Learning Outcomes:
1. Using callback-based demuxer for custom data sources
2. Managing video data buffers and chunk sizes efficiently
3. Implementing proper buffer position tracking and EOF handling
4. Working with both device and host memory for decoded frames


Usage: python decode_from_memory_buffer.py -i <input_file> -o <output_file>
Example: python decode_from_memory_buffer.py -i input.mp4 -o output.yuv

Arguments:
  -i: Input video file
  -o: Output raw video file (default: <input_name>.yuv)
  -d: Use device memory (1) or host memory (0) (default: 1)
  -g: GPU ID to use (default: 0)
  -f: Number of frames to decode (optional)

'''


from pathlib import Path
import PyNvVideoCodec as nvc
import sys
from os.path import join, dirname, abspath

# Add the parent directory to Python path in a way that works from any working directory
current_dir = dirname(abspath(__file__))
parent_dir = dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Import utilities for decoding
from utils.decode_parser import parse_decode_args
from utils.Utils import get_frame_data
from utils.backend_utils import context_stream_kwargs



class VideoStreamFeeder:
    """
    Class to handle feeding video data in chunks to the demuxer.

    This class reads a video file into memory and provides a method to feed
    chunks of data to the demuxer buffer.
    """
    def __init__(self, file_path):
        """
        Initialize the VideoStreamFeeder with a video file.

        Args:
            file_path (str): Path to the video file to be read
        """
        with open(file_path, 'rb') as f:
            self.video_buffer = bytearray(f.read())
        self.current_pos = 0
        self.bytes_remaining = len(self.video_buffer)
        self.chunk_size = 0

    def feed_chunk(self, demuxer_buffer):
        """
        Feed next chunk of video data to demuxer buffer.

        Args:
            demuxer_buffer: Pre-allocated buffer provided by demuxer

        Returns:
            int: Number of bytes copied to buffer, 0 if no more data
        """
        buffer_capacity = len(demuxer_buffer)

        if self.bytes_remaining < buffer_capacity:
            self.chunk_size = self.bytes_remaining
        else:
            self.chunk_size = buffer_capacity

        if self.chunk_size == 0:
            return 0

        demuxer_buffer[:] = self.video_buffer[self.current_pos:self.current_pos + self.chunk_size]

        self.current_pos += self.chunk_size
        self.bytes_remaining -= self.chunk_size
        return self.chunk_size


def decode_from_byte_array(input_file, yuv_file, use_device_memory, gpu_id, frame_count=None):
    """
    Implement buffer-based pipeline that reads the input file in chunks.

    This function demonstrates how to decode video by processing data directly
    from memory buffers instead of reading from disk.

    Parameters:
        input_file (str): Path to the input video file to be decoded
        yuv_file (str): Path where the buffer-based pipeline output will be saved
        use_device_memory (int): If set to 1, output decoded frame is device pointer wrapped in backend array interface
        gpu_id (int): GPU device ID to use
        frame_count (int, optional): Maximum number of frames to decode. If None, 0, or negative, decode all frames.

    Returns:
        None: Decoded frames are written to a raw file.
    """
    try:
        print("Starting buffer-based decoding...")
        data_feeder = VideoStreamFeeder(input_file)
        buffer_demuxer = nvc.CreateDemuxer(data_feeder.feed_chunk)

        buffer_decoder = nvc.CreateDecoder(
            gpuid=gpu_id,
            codec=buffer_demuxer.GetNvCodecId(),
            **context_stream_kwargs(nvc, context=0, stream=0),
            usedevicememory=use_device_memory
        )

        # Normalize frame count
        decode_all = frame_count is None or frame_count <= 0
        if decode_all:
            print("Decoding all available frames")
            frame_count = None

        frames_decoded = 0

        with open(yuv_file, 'wb') as decFile:
            for packet in buffer_demuxer:
                for decoded_frame in buffer_decoder.Decode(packet):

                    frame_data = get_frame_data(decoded_frame, use_device_memory)
                    decFile.write(bytearray(frame_data))

                    frames_decoded += 1
                    if frame_count is not None and frames_decoded >= frame_count:
                        print(f"Successfully decoded requested {frame_count} frames to {yuv_file}")
                        return

            # If we get here, we've decoded all available frames
            if frame_count is not None and frames_decoded < frame_count:
                print(f"Warning: Video ended before reaching requested frame count. Requested: {frame_count}, Decoded: {frames_decoded}")
                print(f"Decoded frames written to {yuv_file}")
            else:
                print(f"Successfully decoded all {frames_decoded} frames to {yuv_file}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":

    args = parse_decode_args(
        "Demonstrates video demuxing by processing video data directly from memory buffers."
    )

    print("=" * 60)
    print("Configuration:")
    print(f"Input: {args.encoded_file_path}")
    print(f"Output: {args.raw_file_path}")
    print(f"GPU ID: {args.gpu_id}")
    print(f"Use Device Memory: {args.use_device_memory}")
    print(f"Frame Count: {args.frame_count if args.frame_count else 'All frames'}")
    print("=" * 60)

    decode_from_byte_array(
        input_file=args.encoded_file_path,
        yuv_file=args.raw_file_path,
        use_device_memory=args.use_device_memory,
        gpu_id=args.gpu_id,
        frame_count=args.frame_count,
    )
