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

"""Backend compatibility helpers for CUDA and MUSA samples."""

from typing import Any, Dict


def is_musa_build(nvc: Any) -> bool:
    """Return True when the imported PyNvVideoCodec build is MUSA-based."""
    return getattr(nvc, "__backend__", "") == "musa"


def context_stream_kwargs(nvc: Any, context: int = 0, stream: int = 0) -> Dict[str, int]:
    """Return the stable public context/stream keyword arguments."""
    return {"cudacontext": int(context), "cudastream": int(stream)}


def set_decoder_session_count(nvc: Any, count: int) -> None:
    """Set decoder session count when the backend exposes decoder session controls."""
    decoder_cls = getattr(nvc, "PyNvDecoder", None)

    if decoder_cls is None or not hasattr(decoder_cls, "SetSessionCount"):
        if is_musa_build(nvc):
            print(f"Decoder session count is not exposed for MUSA; continuing without SetSessionCount({count})")
            return
        raise AttributeError("Backend module does not expose SetSessionCount")

    decoder_cls.SetSessionCount(count)


def is_mpeg2_codec(nvc: Any, codec: Any) -> bool:
    """Return True when a backend-specific codec enum value represents MPEG2."""
    codec_enum = getattr(nvc, "cudaVideoCodec", None)
    if codec_enum is not None and hasattr(codec_enum, "MPEG2"):
        return codec == codec_enum.MPEG2
    return str(codec).endswith(".MPEG2")
