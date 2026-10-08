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
Core module for handling decode statistics.

This module provides functionality for extracting and analyzing low-level video decoding 
statistics from H.264/H.265 streams. The following statistics are collected and analyzed:

1. QP (Quantization Parameter) Analysis:
   - Average, min, max QP values per frame
   - Indicates compression level and quality trade-offs
   - Higher QP = more compression, potentially lower quality

2. CU (Coding Unit) Type Distribution:
   - INTRA: Spatial prediction (current frame only)
   - INTER: Temporal prediction (motion compensation)
   - SKIP: Copy from reference without residual
   - PCM: Uncompressed raw pixel values

3. Motion Vector Statistics:
   - MV0: Primary motion vectors (L0 reference)
   - MV1: Secondary motion vectors (L1 reference, B-frames)
   - Magnitude analysis for temporal complexity assessment

4. Macroblock Details:
   - Per-block encoding decisions and parameters
   - Motion vector coordinates and directions
   - QP values and prediction types for debugging

These statistics are valuable for:
- Video quality analysis
- Encoder behavior understanding
- Performance optimization
- Debugging encoding/decoding issues
"""

# CU type definitions and mapping
CU_TYPES = {
    0: "INTRA",
    1: "INTER", 
    2: "SKIP",
    3: "PCM",
    7: "INVALID"
}

class DecodeStatsWriter:
    """Handles writing of decode statistics to output files."""
    
    def __init__(self, output_file):
        """Initialize with output file handle."""
        self.output_file = output_file

    def write_frame_stats(self, frame_idx, parsed_stats):
        """Write all statistics for a single frame."""
        if not parsed_stats or len(parsed_stats) == 0:
            self._write_frame_header(frame_idx)
            self.output_file.write("No decode stats available\n")
            return

        self._write_frame_header(frame_idx)
        
        qp_luma_list = parsed_stats["qp_luma"]
        if not qp_luma_list or len(qp_luma_list) == 0:
            self.output_file.write("No macroblock statistics available\n")
            return

        num_blocks = len(qp_luma_list)
        self.output_file.write(f"Macroblock Statistics ({num_blocks} blocks):\n")
        
        # Write all block statistics
        self._write_qp_stats(qp_luma_list)
        self._write_cu_distribution(parsed_stats["cu_type"], num_blocks)
        self._write_motion_stats(parsed_stats)
        self._write_detailed_blocks(parsed_stats, num_blocks)

    def _write_frame_header(self, frame_idx):
        """Write frame header with index."""
        self.output_file.write(f"\n=== Frame {frame_idx} ===\n")

    def _write_qp_stats(self, qp_luma_list):
        """Write QP statistics summary."""
        avg_qp = sum(qp_luma_list) / len(qp_luma_list)
        self.output_file.write(f"  Average Luma QP: {avg_qp:.2f}\n")
        self.output_file.write(f"  Min Luma QP: {min(qp_luma_list)}, Max Luma QP: {max(qp_luma_list)}\n")

    def _write_cu_distribution(self, cu_type_list, num_blocks):
        """Write CU type distribution."""
        cu_counts = {}
        for i in range(num_blocks):
            if i < len(cu_type_list):
                cu_type = int(cu_type_list[i])
                cu_counts[cu_type] = cu_counts.get(cu_type, 0) + 1

        if cu_counts:
            self.output_file.write("  CU Type Distribution:\n")
            for cu_type, count in sorted(cu_counts.items()):
                percentage = (count / num_blocks) * 100
                cu_name = CU_TYPES.get(cu_type, f"UNKNOWN_{cu_type}")
                self.output_file.write(f"    {cu_name} (Type {cu_type}): {count} blocks ({percentage:.1f}%)\n")

    def _write_motion_stats(self, parsed_stats):
        """Write motion vector statistics."""
        mv_0, mv_1 = self._calculate_mv_magnitudes(parsed_stats)
        
        if mv_0:
            self.output_file.write(f"  Motion Vector Statistics (INTER and B blocks):\n")
            self.output_file.write(f"    Average MV0 Magnitude: {sum(mv_0) / len(mv_0):.2f}\n")
            self.output_file.write(f"    Max MV0 Magnitude: {max(mv_0):.2f}\n")
        
        if mv_1:
            self.output_file.write(f"    Average MV1 Magnitude: {sum(mv_1) / len(mv_1):.2f}\n")
            self.output_file.write(f"    Max MV1 Magnitude: {max(mv_1):.2f}\n")

    def _calculate_mv_magnitudes(self, parsed_stats):
        """Calculate motion vector magnitudes for INTER blocks."""
        mv_0, mv_1 = [], []
        cu_type_list = parsed_stats["cu_type"]
        
        for i in range(len(cu_type_list)):
            if int(cu_type_list[i]) != 1:  # Skip non-INTER blocks
                continue
                
            # Calculate MV0 magnitude
            if i < len(parsed_stats["mv0_x"]) and i < len(parsed_stats["mv0_y"]):
                mv_x = float(parsed_stats["mv0_x"][i])
                mv_y = float(parsed_stats["mv0_y"][i])
                mv_0.append((mv_x * mv_x + mv_y * mv_y) ** 0.5)
            
            # Calculate MV1 magnitude
            if i < len(parsed_stats["mv1_x"]) and i < len(parsed_stats["mv1_y"]):
                mv_x = float(parsed_stats["mv1_x"][i])
                mv_y = float(parsed_stats["mv1_y"][i])
                mv_1.append((mv_x * mv_x + mv_y * mv_y) ** 0.5)
        
        return mv_0, mv_1

    def _write_detailed_blocks(self, parsed_stats, num_blocks, max_blocks=5):
        """Write detailed information for first few blocks."""
        self.output_file.write(f"  Detailed Macroblock Information (first {max_blocks} blocks):\n")
        
        for i in range(min(max_blocks, num_blocks)):
            # Get block type and QP
            cu_type = int(parsed_stats["cu_type"][i]) if i < len(parsed_stats["cu_type"]) else "UNKNOWN"
            qp_luma = int(parsed_stats["qp_luma"][i]) if i < len(parsed_stats["qp_luma"]) else "UNKNOWN"
            
            # Build motion vector info string
            mv_info = []
            if i < len(parsed_stats["mv0_x"]) and i < len(parsed_stats["mv0_y"]):
                mv_info.append(f"MV0=({int(parsed_stats['mv0_x'][i])}, {int(parsed_stats['mv0_y'][i])})")
            if i < len(parsed_stats["mv1_x"]) and i < len(parsed_stats["mv1_y"]):
                mv_info.append(f"MV1=({int(parsed_stats['mv1_x'][i])}, {int(parsed_stats['mv1_y'][i])})")
            
            mv_str = ", ".join(mv_info) if mv_info else "No MVs"
            cu_name = CU_TYPES.get(cu_type, f"UNKNOWN_{cu_type}")
            
            self.output_file.write(f"    Block {i}: QP={qp_luma}, Type={cu_name}, {mv_str}\n")
