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
Argument parsing utilities for transcoding applications.
"""

import argparse
import os
from os.path import join, dirname, abspath

def add_transcode_args(parser):
    """Add transcoding-specific arguments to an argument parser.

    Args:
        parser (argparse.ArgumentParser): The parser to add arguments to

    Returns:
        None
    """
    parser.add_argument("-i", "--input_file_path", required=True, type=str,
                       help="Path to input video file")
    
    parser.add_argument("-s", "--segments_file_path", type=str,
                       default=join(dirname(dirname(__file__)),"basic", "segments.txt"),
                       help="Path to segments file (format: 'start_time end_time' per line)")
    
    parser.add_argument("-c", "--config_file_path", type=str,
                       default=join(dirname(dirname(__file__)),"basic", "transcode_config.json"),
                       help="Path to transcoder config JSON file")
    
    parser.add_argument("-o", "--output_template", type=str,
                       default="{input_file_name}_segment",
                       help="Output filename template")
    
    parser.add_argument("-g", "--gpu_id", type=int, default=0,
                       help="GPU ID to use (default: 0)")

def parse_transcode_args(description):
    """Parse command line arguments for transcoding applications.

    Args:
        description (str): Description of the application

    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(description=description)
    add_transcode_args(parser)
    return parser.parse_args()
