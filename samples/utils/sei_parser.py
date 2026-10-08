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
SEI message structures and parsing utilities.
"""

import ctypes
import pickle
import os
from os.path import join, dirname, abspath
import PyNvVideoCodec as nvc

# Constants
MAX_CLOCK_TS = 3

class TIMECODESET(ctypes.Structure):
    """Structure for time code set information."""
    _fields_ = [
        ("time_offset_value", ctypes.c_uint32),  # unsigned int
        ("n_frames", ctypes.c_uint16),  # unsigned short
        ("clock_timestamp_flag", ctypes.c_uint8),  # unsigned char
        ("units_field_based_flag", ctypes.c_uint8),  # unsigned char
        ("counting_type", ctypes.c_uint8),  # unsigned char
        ("full_timestamp_flag", ctypes.c_uint8),  # unsigned char
        ("discontinuity_flag", ctypes.c_uint8),  # unsigned char
        ("cnt_dropped_flag", ctypes.c_uint8),  # unsigned char
        ("seconds_value", ctypes.c_uint8),  # unsigned char
        ("minutes_value", ctypes.c_uint8),  # unsigned char
        ("hours_value", ctypes.c_uint8),  # unsigned char
        ("seconds_flag", ctypes.c_uint8),  # unsigned char
        ("minutes_flag", ctypes.c_uint8),  # unsigned char
        ("hours_flag", ctypes.c_uint8),  # unsigned char
        ("time_offset_length", ctypes.c_uint8),  # unsigned char
        ("reserved", ctypes.c_uint8),  # unsigned char
    ]

    def __repr__(self):
        return (
            "TIMECODESET(\n"
            f"    time_offset_value={self.time_offset_value},\n"
            f"    n_frames={self.n_frames},\n"
            f"    clock_timestamp_flag={self.clock_timestamp_flag},\n"
            f"    units_field_based_flag={self.units_field_based_flag},\n"
            f"    counting_type={self.counting_type},\n"
            f"    full_timestamp_flag={self.full_timestamp_flag},\n"
            f"    discontinuity_flag={self.discontinuity_flag},\n"
            f"    cnt_dropped_flag={self.cnt_dropped_flag},\n"
            f"    seconds_value={self.seconds_value},\n"
            f"    minutes_value={self.minutes_value},\n"
            f"    hours_value={self.hours_value},\n"
            f"    seconds_flag={self.seconds_flag},\n"
            f"    minutes_flag={self.minutes_flag},\n"
            f"    hours_flag={self.hours_flag},\n"
            f"    time_offset_length={self.time_offset_length},\n"
            f"    reserved={self.reserved}\n"
            ")"
        )

class TIMECODE(ctypes.Structure):
    """Structure for time code information."""
    _fields_ = [
        ("time_code_set", TIMECODESET * MAX_CLOCK_TS),  # Array of TIMECODESET
        ("num_clock_ts", ctypes.c_uint8),  # unsigned char
    ]

    def __repr__(self):
        time_code_set_repr = ",\n        ".join(
            repr(self.time_code_set[i]) for i in range(self.num_clock_ts)
        )
        return (
            "TIMECODE(\n"
            f"    time_code_set=[\n        {time_code_set_repr}\n    ],\n"
            f"    num_clock_ts={self.num_clock_ts}\n"
            ")"
        )

class SEICONTENTLIGHTLEVELINFO(ctypes.Structure):
    """Structure for content light level information."""
    _fields_ = [
        ("max_content_light_level", ctypes.c_uint16),  # unsigned short
        ("max_pic_average_light_level", ctypes.c_uint16),  # unsigned short
        ("reserved", ctypes.c_uint32),  # unsigned int
    ]

    def __repr__(self):
        return (
            "SEICONTENTLIGHTLEVELINFO(\n"
            f"    max_content_light_level={self.max_content_light_level},\n"
            f"    max_pic_average_light_level={self.max_pic_average_light_level},\n"
            f"    reserved={self.reserved}\n"
            ")"
        )

class SEIMASTERINGDISPLAYINFO(ctypes.Structure):
    """Structure for mastering display information."""
    _fields_ = [
        ("display_primaries_x", ctypes.c_uint16 * 3),  # Array of 3 unsigned short
        ("display_primaries_y", ctypes.c_uint16 * 3),  # Array of 3 unsigned short
        ("white_point_x", ctypes.c_uint16),  # unsigned short
        ("white_point_y", ctypes.c_uint16),  # unsigned short
        ("max_display_mastering_luminance", ctypes.c_uint32),  # unsigned int
        ("min_display_mastering_luminance", ctypes.c_uint32),  # unsigned int
    ]

    def __repr__(self):
        return (
            "SEIMASTERINGDISPLAYINFO(\n"
            f"    display_primaries_x={list(self.display_primaries_x)},\n"
            f"    display_primaries_y={list(self.display_primaries_y)},\n"
            f"    white_point_x={self.white_point_x},\n"
            f"    white_point_y={self.white_point_y},\n"
            f"    max_display_mastering_luminance={self.max_display_mastering_luminance},\n"
            f"    min_display_mastering_luminance={self.min_display_mastering_luminance}\n"
            ")"
        )
    
class TIMECODEMPEG2(ctypes.Structure):
    """Structure for MPEG2 time code information."""
    _fields_ = [
        ("drop_frame_flag", ctypes.c_uint8),  # unsigned char
        ("time_code_hours", ctypes.c_uint8),  # unsigned char
        ("time_code_minutes", ctypes.c_uint8),  # unsigned char
        ("marker_bit", ctypes.c_uint8),  # unsigned char
        ("time_code_seconds", ctypes.c_uint8),  # unsigned char
        ("time_code_pictures", ctypes.c_uint8),  # unsigned char
    ]

    def __repr__(self):
        return (
            "TIMECODEMPEG2(\n"
            f"    drop_frame_flag={self.drop_frame_flag},\n"
            f"    time_code_hours={self.time_code_hours},\n"
            f"    time_code_minutes={self.time_code_minutes},\n"
            f"    marker_bit={self.marker_bit},\n"
            f"    time_code_seconds={self.time_code_seconds},\n"
            f"    time_code_pictures={self.time_code_pictures}\n"
            ")"
        )

class SEIALTERNATIVETRANSFERCHARACTERISTICS(ctypes.Structure):
    """Structure for alternative transfer characteristics."""
    _fields_ = [
        ("preferred_transfer_characteristics", ctypes.c_uint8),  # unsigned char
    ]
    
    def __repr__(self):
        return f"SEIALTERNATIVETRANSFERCHARACTERISTICS(preferred_transfer_characteristics={self.preferred_transfer_characteristics})"

def write_sei_messages(sei_messages, sei_file_path, script_dir=None):
    """
    Write SEI messages to output files.

    This function writes SEI messages in three formats:
    1. sei_message.bin - Raw binary SEI messages
    2. sei_type_message.bin - Pickled SEI type information
    3. sei_message.txt - Human-readable parsed SEI content

    Parameters:
        sei_messages (list): List of tuples containing (sei_info, sei_message)
        sei_file_path (str): Path to output file (base name for all three files)
        script_dir (str, optional): Directory for type message file. If None, uses sei_file_path's directory.

    Returns:
        None
    """
    # Determine output paths
    if script_dir is None:
        script_dir = dirname(abspath(sei_file_path))
    
    sei_type_message_path = join(script_dir, "sei_type_message.bin")
    
    # Open files for storing SEI data
    with open(sei_file_path, "wb") as file_message, \
         open(sei_type_message_path, "wb") as file_type_message:
        
        for sei_info, sei_message in sei_messages:
            sei_type = sei_info["sei_type"]
            sei_uncompressed = sei_info["sei_uncompressed"]
            
            if sei_uncompressed == 1:
                buffer = (ctypes.c_ubyte * len(sei_message))(*sei_message)
                sei_struct = None
                
                # Handle different SEI message types
                if sei_type in (nvc.SEI_TYPE.TIME_CODE_H264, nvc.SEI_TYPE.TIME_CODE):
                    sei_struct = ctypes.cast(
                        buffer,
                        ctypes.POINTER(TIMECODEMPEG2 if codec_id == nvc.cudaVideoCodec.MPEG2 else TIMECODE)
                    ).contents
                elif sei_type == nvc.SEI_TYPE.MASTERING_DISPLAY_COLOR_VOLUME:
                    sei_struct = ctypes.cast(buffer, ctypes.POINTER(SEIMASTERINGDISPLAYINFO)).contents
                elif sei_type == nvc.SEI_TYPE.CONTENT_LIGHT_LEVEL_INFO:
                    sei_struct = ctypes.cast(buffer, ctypes.POINTER(SEICONTENTLIGHTLEVELINFO)).contents
                elif sei_type == nvc.SEI_TYPE.ALTERNATIVE_TRANSFER_CHARACTERISTICS:
                    sei_struct = ctypes.cast(buffer, ctypes.POINTER(SEIALTERNATIVETRANSFERCHARACTERISTICS)).contents
                
                if sei_struct:
                    print(sei_struct)
                    
            file_message.write(bytearray(sei_message))
        pickle.dump(sei_messages, file_type_message)
        print(f"SEI message written to {sei_file_path}")