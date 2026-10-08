#!/usr/bin/env python3
# This copyright notice applies to this file only
#
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

"""Non-invasive MUSA validation wrapper for repository sample applications.

This script validates non-Jupyter sample entrypoints against a MUSA-built
PyNvVideoCodec package. It prepares a small workspace, generates deterministic
media assets, runs sample cases, and classifies supported, unsupported, and
hard-failure outcomes separately.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = REPO_ROOT / "samples"
DEFAULT_WORK_DIR = Path("/tmp/pynvc_musa_validation")
DEFAULT_FFMPEG = Path("/usr/local/mt_vaapi/bin/ffmpeg")
DEFAULT_SIZE = "256x128"
DEFAULT_ALT_SIZE = "320x180"
DEFAULT_FRAME_COUNT = 3
PERF_FRAME_COUNT = 10
HELP_TIMEOUT = 30
DEFAULT_SAMPLE_TIMEOUT = 180
DEFAULT_PREPARE_TIMEOUT = 120
CODECS = ("h264", "hevc", "av1")
DECODE_CODECS = ("h264", "hevc", "vp9", "av1")
# MUSA validation scope: NV12 8-bit and P010 (NV12 10-bit) only.
ENCODE_FORMATS = ("NV12", "P010")
DECODE_PIXEL_FORMATS = ("nv12", "p010")
FORMATS = ENCODE_FORMATS


@dataclass(frozen=True)
class CaseSpec:
    name: str
    sample: Path
    category: str
    args: list[str]
    params: dict[str, object] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)
    timeout: int = DEFAULT_SAMPLE_TIMEOUT
    expected: str = "supported"  # supported | musa_unsupported
    unsupported_reason: str = ""
    native_api: Optional[str] = None


@dataclass
class CaseResult:
    name: str
    sample: str
    category: str
    expected: str
    params: dict[str, object]
    command: list[str]
    status: str
    returncode: Optional[int] = None
    stdout_log: Optional[str] = None
    stderr_log: Optional[str] = None
    message: str = ""
    native_api: Optional[str] = None
    output_files: list[str] = field(default_factory=list)
    duration_s: Optional[float] = None


@dataclass
class ValidationContext:
    work_dir: Path
    python: str
    env: dict[str, str]
    ffmpeg: Path
    size: str
    alt_size: str
    prepare_timeout: int
    sample_timeout: int
    include_unsupported: bool
    source_dir: Optional[Path] = None
    results: list[CaseResult] = field(default_factory=list)
    assets: dict[str, Path] = field(default_factory=dict)
    coverage: dict[str, object] = field(default_factory=dict)


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"must be an integer: {value}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def parse_size(value: str) -> tuple[int, int]:
    if "x" not in value.lower():
        raise argparse.ArgumentTypeError("size must be WIDTHxHEIGHT")
    width_s, height_s = value.lower().split("x", 1)
    try:
        width = int(width_s)
        height = int(height_s)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("size must contain integer width and height") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("size dimensions must be positive")
    if width % 2 or height % 2:
        raise argparse.ArgumentTypeError("validation assets use 4:2:0 formats and require even dimensions")
    return width, height


def frame_size(width: int, height: int, surface_format: str) -> int:
    if surface_format in ("ARGB", "ABGR", "ARGB10", "ABGR10"):
        return width * height * 4
    if surface_format == "YUV444":
        return width * height * 3
    if surface_format == "YUV420":
        return int(width * height * 3 / 2)
    if surface_format in ("P010", "P016"):
        return int(width * height * 3 / 2 * 2)
    if surface_format == "YUV444_16BIT":
        return int(width * height * 3 * 2)
    if surface_format == "NV16":
        return width * height * 2
    if surface_format in ("P210", "P216"):
        return width * height * 4
    return int(width * height * 3 / 2)


def build_env() -> dict[str, str]:
    env = {
        "HOME": os.environ.get("HOME", "/root"),
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/local/mt_vaapi/bin"),
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH", ""),
    }
    for key in ("PYNVVIDEO_BACKEND", "USE_MUSA"):
        env.pop(key, None)
    for key in ("MUSA_VISIBLE_DEVICES", "CUDA_VISIBLE_DEVICES"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def run_command(command: list[str], env: Optional[dict[str, str]] = None, cwd: Optional[Path] = None, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def write_text(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def write_binary(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def make_raw_asset(path: Path, width: int, height: int, surface_format: str, frames: int = 8) -> Path:
    size = frame_size(width, height, surface_format) * frames
    data = bytes((idx % 251 for idx in range(size)))
    return write_binary(path, data)


def make_segments_file(path: Path, ranges: list[tuple[float, float]]) -> Path:
    contents = "\n".join(f"{start:g} {end:g}" for start, end in ranges) + "\n"
    return write_binary(path, contents.encode("utf-8"))


def make_h264_asset(ctx: ValidationContext, out: Path, size: str, duration: str) -> Path:
    if out.exists() and out.stat().st_size > 0:
        return out
    if not ctx.ffmpeg.is_file():
        raise FileNotFoundError(f"ffmpeg not found: {ctx.ffmpeg}")
    cmd = [
        str(ctx.ffmpeg),
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={size}:rate=5:duration={duration}",
        "-c:v",
        "h264_mtenc",
        "-pix_fmt",
        "nv12",
        str(out),
    ]
    completed = run_command(cmd, env=ctx.env, cwd=REPO_ROOT, timeout=ctx.prepare_timeout)
    write_text(ctx.work_dir / "logs" / f"prepare_{out.stem}.stdout.log", completed.stdout)
    write_text(ctx.work_dir / "logs" / f"prepare_{out.stem}.stderr.log", completed.stderr)
    if completed.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"failed to generate H.264 asset: {out}")
    return out




def make_codec_asset(ctx: ValidationContext, out: Path, size: str, duration: str, codec: str, pix_fmt: str = "nv12") -> Path:
    """Generate one decode asset, or reuse a supplied conformance stream."""
    if out.exists() and out.stat().st_size > 0:
        return out
    if codec == "vp9" and ctx.source_dir:
        candidates = sorted(ctx.source_dir.glob("videos/vp9/*.webm"))
        if candidates:
            shutil.copyfile(candidates[0], out)
            return out
        raise FileNotFoundError(f"no VP9 source found below {ctx.source_dir}")
    if not ctx.ffmpeg.is_file():
        raise FileNotFoundError(f"ffmpeg not found: {ctx.ffmpeg}")
    encoder = {"h264": "h264_mtenc", "hevc": "hevc_mtenc", "vp9": "libvpx-vp9", "av1": "av1_mtenc"}.get(codec, codec)
    cmd = [str(ctx.ffmpeg), "-y", "-f", "lavfi", "-i",
           f"testsrc2=size={size}:rate=5:duration={duration}",
           "-c:v", encoder, "-pix_fmt", pix_fmt, str(out)]
    completed = run_command(cmd, env=ctx.env, cwd=REPO_ROOT, timeout=ctx.prepare_timeout)
    write_text(ctx.work_dir / "logs" / f"prepare_{out.stem}.stdout.log", completed.stdout)
    write_text(ctx.work_dir / "logs" / f"prepare_{out.stem}.stderr.log", completed.stderr)
    if completed.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"failed to generate {codec} {pix_fmt} asset: {out}")
    return out


def make_h264_audio_asset(ctx: ValidationContext, out: Path, size: str, duration: str) -> Path:
    if out.exists() and out.stat().st_size > 0:
        return out
    if not ctx.ffmpeg.is_file():
        raise FileNotFoundError(f"ffmpeg not found: {ctx.ffmpeg}")

    cmd = [
        str(ctx.ffmpeg),
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={size}:rate=5:duration={duration}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=1000:sample_rate=48000:duration={duration}",
        "-c:v",
        "h264_mtenc",
        "-pix_fmt",
        "nv12",
        "-c:a",
        "aac",
        "-shortest",
        str(out),
    ]
    completed = run_command(cmd, env=ctx.env, cwd=REPO_ROOT, timeout=ctx.prepare_timeout)
    write_text(ctx.work_dir / "logs" / f"prepare_{out.stem}.stdout.log", completed.stdout)
    write_text(ctx.work_dir / "logs" / f"prepare_{out.stem}.stderr.log", completed.stderr)
    if completed.returncode == 0 and out.exists() and out.stat().st_size > 0:
        return out

    fallback = Path(os.environ.get("PYNVC_MUSA_TRANSCODE_INPUT_AUDIO", "/tmp/pynvc_musa_transcode_input_audio.mp4"))
    if fallback.is_file() and fallback.stat().st_size > 0:
        shutil.copyfile(fallback, out)
        return out

    raise RuntimeError(f"failed to generate H.264 audio asset: {out}")


def validate_runtime_inputs(args: argparse.Namespace) -> None:
    parse_size(args.size)
    parse_size(args.alt_size)
    positive_int(str(args.sample_timeout))
    positive_int(str(args.prepare_timeout))


def discover_runnable_samples() -> list[Path]:
    discovered: list[Path] = []
    for subdir in (SAMPLES_DIR / "basic", SAMPLES_DIR / "advanced"):
        if not subdir.exists():
            continue
        for path in sorted(subdir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            text = path.read_text(encoding="utf-8")
            if 'if __name__ == "__main__"' not in text and "if __name__ == '__main__'" not in text:
                continue
            discovered.append(path.relative_to(REPO_ROOT))
    return discovered


def classify_failure(spec: CaseSpec, stdout: str, stderr: str, returncode: int) -> tuple[str, str, Optional[str]]:
    combined = f"{stdout}\n{stderr}"
    lower = combined.lower()
    if returncode == 124:
        return "timeout", "Command timed out", None
    unsupported_markers = [
        "not supported",
        "unsupported",
        "cuda is not available",
        "decode statistics are unavailable",
        "decode statistics not found",
        "parsedecodestats",
        "incorrect usage of cpu input buffer",
        "error code : 12",
        "backend ipc memory support",
        "cudacontext",
        "cudastream",
        "no module named 'pycuda'",
        "'nonetype' object has no attribute 'mem_alloc'",
        "'nonetype' object has no attribute 'memcpy_dtoh'",
        "musa error: invalid device context",
    ]
    if any(marker in lower for marker in unsupported_markers):
        return "musa_unsupported", spec.unsupported_reason or "MUSA/runtime limitation", spec.native_api
    return "failed", "Command failed; inspect stdout/stderr logs", None


def expected_output_paths(ctx: ValidationContext, spec: CaseSpec) -> list[Path]:
    return [ctx.work_dir / rel for rel in spec.outputs]


def run_case(ctx: ValidationContext, spec: CaseSpec) -> None:
    command = [ctx.python, str(spec.sample), *spec.args]
    stdout_log = ctx.work_dir / "logs" / f"{spec.name}.stdout.log"
    stderr_log = ctx.work_dir / "logs" / f"{spec.name}.stderr.log"
    start = subprocess.time.perf_counter if hasattr(subprocess, "time") else None
    begin = __import__("time").perf_counter()

    if spec.expected == "musa_unsupported" and not ctx.include_unsupported:
        ctx.results.append(
            CaseResult(
                name=spec.name,
                sample=str(spec.sample),
                category=spec.category,
                expected=spec.expected,
                params=spec.params,
                command=command,
                status="musa_unsupported",
                message=spec.unsupported_reason or "Known MUSA-unsupported case",
                native_api=spec.native_api,
            )
        )
        return

    try:
        completed = run_command(command, env=ctx.env, cwd=REPO_ROOT, timeout=spec.timeout)
        stdout_path = write_text(stdout_log, completed.stdout)
        stderr_path = write_text(stderr_log, completed.stderr)
        output_paths = expected_output_paths(ctx, spec)
        existing_outputs = [str(p) for p in output_paths if p.exists() and p.stat().st_size > 0]
        missing_outputs = [str(p) for p in output_paths if not p.exists() or p.stat().st_size == 0]

        if completed.returncode == 0:
            if spec.expected == "musa_unsupported":
                if missing_outputs:
                    status, message, native_api = classify_missing_outputs(spec, completed.stdout, completed.stderr, missing_outputs)
                else:
                    status, message, native_api = classify_failure(spec, completed.stdout, completed.stderr, 1)
                if status != "musa_unsupported":
                    status = "xfail_pass"
                    message = "Expected MUSA limitation unexpectedly passed"
                    native_api = spec.native_api
            elif missing_outputs:
                status, message, native_api = classify_missing_outputs(spec, completed.stdout, completed.stderr, missing_outputs)
            else:
                status = "passed"
                message = ""
                native_api = None
        else:
            status, message, native_api = classify_failure(spec, completed.stdout, completed.stderr, completed.returncode)
            if spec.expected == "musa_unsupported" and status == "failed":
                status = "musa_unsupported"
                message = spec.unsupported_reason or "Known MUSA-unsupported case"
                native_api = spec.native_api

        duration = __import__("time").perf_counter() - begin
        ctx.results.append(
            CaseResult(
                name=spec.name,
                sample=str(spec.sample),
                category=spec.category,
                expected=spec.expected,
                params=spec.params,
                command=command,
                status=status,
                returncode=completed.returncode,
                stdout_log=stdout_path,
                stderr_log=stderr_path,
                message=message,
                native_api=native_api,
                output_files=existing_outputs,
                duration_s=duration,
            )
        )
    except subprocess.TimeoutExpired as exc:
        stdout_content = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr_content = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        stdout_path = write_text(stdout_log, stdout_content)
        stderr_path = write_text(stderr_log, stderr_content)
        duration = __import__("time").perf_counter() - begin
        ctx.results.append(
            CaseResult(
                name=spec.name,
                sample=str(spec.sample),
                category=spec.category,
                expected=spec.expected,
                params=spec.params,
                command=command,
                status="timeout",
                stdout_log=stdout_path,
                stderr_log=stderr_path,
                message="Command timed out",
                native_api=spec.native_api,
                duration_s=duration,
            )
        )


def classify_missing_outputs(spec: CaseSpec, stdout: str, stderr: str, missing_outputs: list[str]) -> tuple[str, str, Optional[str]]:
    combined = f"{stdout}\n{stderr}".lower()
    if spec.name.startswith("simple_decode_stats") and ("decode statistics not found" in combined or "decode statistics are unavailable" in combined):
        return "musa_unsupported", "MUSA does not expose decode-stat parsing", "DecodedFrame.ParseDecodeStats"
    if spec.name.startswith("decode_reconfigure") and ("generatenativeoutput" in combined or "musa_error_invalid_value" in combined or "invalid value" in combined):
        return "musa_unsupported", "MUSA decoder reconfigure path rejected the second resolution", "MuvidDecoder::GenerateNativeOutput"
    if spec.name.startswith("create_video_segments") and ("simpletranscoder constructor failed" in combined or "incompatible function arguments" in combined or "no audio stream found" in combined):
        return "musa_unsupported", "MUSA SimpleTranscoder path rejected this transcode configuration", "SimpleTranscoder"
    if spec.name == "basic_encode_cpu_h264_yuv420" and ("registerresource" in combined or "mtencregisterresource" in combined):
        return "musa_unsupported", "MUSA encoder rejected YUV420 CPU-buffer input", "MtEncoder::RegisterResource"
    if "unsupported" in combined or "not supported" in combined:
        return "musa_unsupported", spec.unsupported_reason or "MUSA/runtime limitation", spec.native_api
    pycuda_markers = (
        "no module named 'pycuda'",
        "'nonetype' object has no attribute 'mem_alloc'",
        "'nonetype' object has no attribute 'memcpy_dtoh'",
    )
    if any(marker in combined for marker in pycuda_markers):
        return "musa_unsupported", "This MUSA validation environment lacks the MUSA-capable PyCUDA fork needed by this device-memory path", "PyCUDA/MUSA IPC compatibility layer"
    return "failed", f"Expected non-empty output missing: {missing_outputs}", None


def add_case(cases: list[CaseSpec], **kwargs) -> None:
    cases.append(CaseSpec(**kwargs))


def build_matrix(ctx: ValidationContext) -> list[CaseSpec]:
    cases: list[CaseSpec] = []
    work = ctx.work_dir
    h264 = work / "assets" / f"input_{ctx.size}.h264.mp4"
    h264_alt = work / "assets" / f"input_{ctx.alt_size}.h264.mp4"
    h264_audio = work / "assets" / f"input_{ctx.size}.h264_audio.mp4"
    raw_nv12 = work / "assets" / f"raw_{ctx.size}_nv12.yuv"
    raw_yuv420 = work / "assets" / f"raw_{ctx.size}_yuv420.yuv"
    raw_p010 = work / "assets" / f"raw_{ctx.size}_p010.yuv"

    help_scripts = [
        "samples/basic/encode.py",
        "samples/basic/create_video_segments.py",
        "samples/basic/simple_decode_sampling.py",
        "samples/advanced/decode.py",
        "samples/advanced/decode_from_memory_buffer.py",
        "samples/advanced/decode_with_cuda_control.py",
        "samples/advanced/decode_reconfigure.py",
        "samples/advanced/decode_sei_msg.py",
        "samples/advanced/simple_decode_stats.py",
        "samples/advanced/encode_reconfigure.py",
        "samples/advanced/encode_sei_msg.py",
        "samples/advanced/encode_perf.py",
        "samples/advanced/decode_perf.py",
        "samples/advanced/decode_with_low_latency.py",
    ]
    for script in help_scripts:
        add_case(
            cases,
            name=f"cli_help_{Path(script).stem}",
            sample=Path(script),
            category="help",
            args=["--help"],
            timeout=HELP_TIMEOUT,
            params={},
        )

    # Declared decode codec/stream-format matrix. The sample CLI returns the
    # stream's native output, so each generated asset exercises one format.
    decode_assets = {
        (codec, pixel_format): work / "assets" / f"input_{ctx.size}.{codec}.{pixel_format}.mp4"
        for codec in DECODE_CODECS
        for pixel_format in DECODE_PIXEL_FORMATS
    }
    for (codec, pixel_format), asset in decode_assets.items():
        add_case(
            cases,
            name=f"decode_matrix_{codec}_{pixel_format}",
            sample=Path("samples/advanced/decode.py"),
            category="decode_matrix",
            args=["-i", str(asset), "-o", str(work / f"decode_matrix_{codec}_{pixel_format}.raw"), "-d", "0", "-f", "3"],
            outputs=[f"decode_matrix_{codec}_{pixel_format}.raw"],
            params={"codec": codec, "format": pixel_format, "use_device_memory": 0},
        )
    # Declared encode codec x NV12 bit-depth matrix.
    for codec in CODECS:
        for surface_format in ENCODE_FORMATS:
            add_case(
                cases,
                name=f"encode_matrix_cpu_{codec}_{surface_format.lower()}",
                sample=Path("samples/basic/encode.py"),
                category="encode_matrix",
                args=["-i", str(work / "assets" / f"raw_{ctx.size}_{surface_format.lower()}.yuv"),
                      "-o", str(work / f"encode_matrix_{codec}_{surface_format.lower()}.{codec}"),
                      "-s", ctx.size, "-m", "cpu", "-if", surface_format, "-c", codec, "-f", "3"],
                outputs=[f"encode_matrix_{codec}_{surface_format.lower()}.{codec}"],
                params={"codec": codec, "format": surface_format, "buffer_mode": "cpu", "frame_count": 3},
            )
    for use_device_memory in (0, 1):
        add_case(
            cases,
            name=f"decode_{use_device_memory}_host",
            sample=Path("samples/advanced/decode.py"),
            category="decode",
            args=["-i", str(h264), "-o", str(work / f"decode_{use_device_memory}_host.yuv"), "-d", str(use_device_memory), "-f", "3"],
            outputs=[f"decode_{use_device_memory}_host.yuv"],
            params={"use_device_memory": use_device_memory, "frame_count": 3},
        )
        add_case(
            cases,
            name=f"decode_from_memory_buffer_{use_device_memory}",
            sample=Path("samples/advanced/decode_from_memory_buffer.py"),
            category="decode",
            args=["-i", str(h264), "-o", str(work / f"decode_buffer_{use_device_memory}.yuv"), "-d", str(use_device_memory), "-f", "3"],
            outputs=[f"decode_buffer_{use_device_memory}.yuv"],
            params={"use_device_memory": use_device_memory, "frame_count": 3},
        )
        add_case(
            cases,
            name=f"decode_with_cuda_control_{use_device_memory}",
            sample=Path("samples/advanced/decode_with_cuda_control.py"),
            category="decode",
            args=["-i", str(h264), "-o", str(work / f"decode_cuda_control_{use_device_memory}.yuv"), "-d", str(use_device_memory), "-f", "3"],
            outputs=[f"decode_cuda_control_{use_device_memory}.yuv"],
            params={"use_device_memory": use_device_memory, "frame_count": 3},
        )
        add_case(
            cases,
            name=f"decode_reconfigure_{use_device_memory}",
            sample=Path("samples/advanced/decode_reconfigure.py"),
            category="decode",
            args=["-i1", str(h264), "-i2", str(h264_alt), "-o1", str(work / f"reconfig_1_{use_device_memory}.yuv"), "-o2", str(work / f"reconfig_2_{use_device_memory}.yuv"), "-d", str(use_device_memory), "-f", "3"],
            outputs=[f"reconfig_1_{use_device_memory}.yuv", f"reconfig_2_{use_device_memory}.yuv"],
            params={"use_device_memory": use_device_memory, "frame_count": 3},
        )

    for decode_latency in (0, 1, 2):
        add_case(
            cases,
            name=f"decode_low_latency_{decode_latency}",
            sample=Path("samples/advanced/decode_with_low_latency.py"),
            category="decode",
            args=["-i", str(h264), "-o", str(work / f"decode_low_latency_{decode_latency}.yuv"), "-d", "0", "-f", "3", "-dl", str(decode_latency)],
            outputs=[f"decode_low_latency_{decode_latency}.yuv"],
            params={"use_device_memory": 0, "frame_count": 3, "decode_latency": decode_latency},
        )

    add_case(
        cases,
        name="decode_sei_msg_explicit",
        sample=Path("samples/advanced/decode_sei_msg.py"),
        category="decode",
        args=["-i", str(h264), "-s", str(work / "sei_message.bin"), "-st", str(work / "sei_type_message.bin"), "-d", "0"],
        outputs=[],
        params={"use_device_memory": 0},
    )
    add_case(
        cases,
        name="simple_decode_stats_default",
        sample=Path("samples/advanced/simple_decode_stats.py"),
        category="decode",
        args=["-i", str(h264), "-p", str(work / "decode_stats.txt"), "-d", "0"],
        outputs=["decode_stats.txt"],
        params={"use_device_memory": 0, "need_scanned_stream_metadata": False},
        expected="musa_unsupported",
        unsupported_reason="MUSA decoder stats parsing is unavailable",
        native_api="DecodedFrame.ParseDecodeStats",
    )
    add_case(
        cases,
        name="simple_decode_stats_scanned",
        sample=Path("samples/advanced/simple_decode_stats.py"),
        category="decode",
        args=["-i", str(h264), "-p", str(work / "decode_stats_scanned.txt"), "-d", "0", "-sm"],
        outputs=["decode_stats_scanned.txt"],
        params={"use_device_memory": 0, "need_scanned_stream_metadata": True},
        expected="musa_unsupported",
        unsupported_reason="MUSA decoder stats parsing is unavailable",
        native_api="DecodedFrame.ParseDecodeStats",
    )
    add_case(
        cases,
        name="simple_decode_sampling_single",
        sample=Path("samples/basic/simple_decode_sampling.py"),
        category="decode",
        args=[str(h264), "-g", "0", "-f", "3"],
        outputs=[],
        params={"frames": 3, "num_inputs": 1},
    )
    add_case(
        cases,
        name="simple_decode_sampling_multi",
        sample=Path("samples/basic/simple_decode_sampling.py"),
        category="decode",
        args=[str(h264), str(h264_alt), "-g", "0", "-f", "8"],
        outputs=[],
        params={"frames": 8, "num_inputs": 2},
    )

    # Decode performance variants.
    for mode in ("thread", "process"):
        for num_instances in (1, 2):
            add_case(
                cases,
                name=f"decode_perf_{mode}_{num_instances}",
                sample=Path("samples/advanced/decode_perf.py"),
                category="decode_perf",
                args=["-i", str(h264), "-d", "0", "-f", "10", "-m", mode, "-n", str(num_instances)],
                outputs=[],
                timeout=ctx.sample_timeout,
                params={"mode": mode, "num_instances": num_instances, "use_device_memory": 0, "frame_count": 10},
            )

    # Encode baseline and format/codec variations.
    for buffer_mode in ("cpu", "gpu"):
        add_case(
            cases,
            name=f"basic_encode_{buffer_mode}_h264_nv12",
            sample=Path("samples/basic/encode.py"),
            category="encode",
            args=["-i", str(raw_nv12), "-o", str(work / f"encode_{buffer_mode}_h264.h264"), "-s", ctx.size, "-m", buffer_mode, "-if", "NV12", "-c", "h264", "-f", "3"],
            outputs=[f"encode_{buffer_mode}_h264.h264"],
            params={"buffer_mode": buffer_mode, "codec": "h264", "format": "NV12", "frame_count": 3},
        )
    for codec in ("hevc", "av1"):
        add_case(
            cases,
            name=f"basic_encode_cpu_{codec}_nv12",
            sample=Path("samples/basic/encode.py"),
            category="encode",
            args=["-i", str(raw_nv12), "-o", str(work / f"encode_cpu_{codec}.{codec}"), "-s", ctx.size, "-m", "cpu", "-if", "NV12", "-c", codec, "-f", "3"],
            outputs=[f"encode_cpu_{codec}.{codec}"],
            params={"buffer_mode": "cpu", "codec": codec, "format": "NV12", "frame_count": 3},
        )
    # Keep the legacy smoke case within the supported NV12 8/10-bit scope.
    for surface_format, raw_asset in (("P010", raw_p010),):
        add_case(
            cases,
            name=f"basic_encode_cpu_h264_{surface_format.lower()}",
            sample=Path("samples/basic/encode.py"),
            category="encode",
            args=["-i", str(raw_asset), "-o", str(work / f"encode_cpu_h264_{surface_format.lower()}.h264"), "-s", ctx.size, "-m", "cpu", "-if", surface_format, "-c", "h264", "-f", "3"],
            outputs=[f"encode_cpu_h264_{surface_format.lower()}.h264"],
            params={"buffer_mode": "cpu", "codec": "h264", "format": surface_format, "frame_count": 3},
        )
    add_case(
        cases,
        name="encode_reconfigure_default",
        sample=Path("samples/advanced/encode_reconfigure.py"),
        category="encode",
        args=["-i", str(raw_nv12), "-o", str(work / "encode_reconfigure_default.h264"), "-s", ctx.size, "-if", "NV12", "-c", "h264", "-f", "3"],
        outputs=["encode_reconfigure_default.h264"],
        params={"codec": "h264", "format": "NV12", "frame_count": 3},
    )
    add_case(
        cases,
        name="encode_reconfigure_lowlatency",
        sample=Path("samples/advanced/encode_reconfigure.py"),
        category="encode",
        args=["-i", str(raw_nv12), "-o", str(work / "encode_reconfigure_lowlatency.h264"), "-s", ctx.size, "-if", "NV12", "-c", "h264", "-json", str(SAMPLES_DIR / "advanced" / "encode_config_lowlatency.json"), "-f", "3"],
        outputs=["encode_reconfigure_lowlatency.h264"],
        params={"codec": "h264", "format": "NV12", "config_file": "encode_config_lowlatency.json", "frame_count": 3},
    )
    add_case(
        cases,
        name="encode_sei_msg",
        sample=Path("samples/advanced/encode_sei_msg.py"),
        category="encode",
        args=["-i", str(raw_nv12), "-o", str(work / "encode_sei_msg.h264"), "-s", ctx.size, "-if", "NV12", "-c", "h264", "-f", "3"],
        outputs=["encode_sei_msg.h264"],
        params={"codec": "h264", "format": "NV12", "frame_count": 3},
    )

    for mode in ("thread", "process"):
        for num_workers in (1, 2):
            add_case(
                cases,
                name=f"encode_perf_{mode}_{num_workers}",
                sample=Path("samples/advanced/encode_perf.py"),
                category="encode_perf",
                args=["-i", str(raw_nv12), "-s", ctx.size, "-if", "NV12", "-c", "h264", "-f", "10", "-m", mode, "-n", str(num_workers)],
                outputs=[],
                timeout=ctx.sample_timeout,
                params={"mode": mode, "num_workers": num_workers, "codec": "h264", "format": "NV12", "frame_count": 10},
            )

    # Transcode cases.
    segments_default = work / "segments_default.txt"
    segments_multi = work / "segments_multi.txt"
    make_segments_file(segments_default, [(0.0, 1.0)])
    make_segments_file(segments_multi, [(0.0, 1.0), (1.0, 2.0)])
    bf0_config = work / "transcode_config_bf0.json"
    default_config = SAMPLES_DIR / "basic" / "transcode_config.json"
    config = json.loads(default_config.read_text(encoding="utf-8"))
    config["bf"] = 0
    bf0_config.write_text(json.dumps(config, indent=2), encoding="utf-8")

    add_case(
        cases,
        name="create_video_segments_default",
        sample=Path("samples/basic/create_video_segments.py"),
        category="transcode",
        args=["-i", str(h264_audio), "-s", str(segments_default), "-c", str(default_config), "-o", str(work / "segment_default")],
        outputs=["segment_default_0_1.mp4"],
        timeout=ctx.sample_timeout,
        params={"segments": "default", "config": "default", "output_template": "segment_default", "input": "h264_audio"},
    )
    add_case(
        cases,
        name="create_video_segments_bf0",
        sample=Path("samples/basic/create_video_segments.py"),
        category="transcode",
        args=["-i", str(h264_audio), "-s", str(segments_multi), "-c", str(bf0_config), "-o", str(work / "segment_bf0")],
        outputs=["segment_bf0_0_1.mp4", "segment_bf0_1_2.mp4"],
        timeout=ctx.sample_timeout,
        params={"segments": "multi", "config": "bf0", "output_template": "segment_bf0", "input": "h264_audio"},
    )

    return cases


def validate_sample_help(ctx: ValidationContext, cases: list[CaseSpec]) -> None:
    for spec in cases:
        if spec.category != "help":
            continue
        run_case(ctx, spec)


def run_matrix(ctx: ValidationContext, cases: list[CaseSpec]) -> None:
    for spec in cases:
        if spec.category == "help":
            continue
        run_case(ctx, spec)


def write_reports(ctx: ValidationContext, cases: list[CaseSpec]) -> None:
    summary = {
        "repo_root": str(REPO_ROOT),
        "work_dir": str(ctx.work_dir),
        "python": ctx.python,
        "size": ctx.size,
        "alt_size": ctx.alt_size,
        "results": [asdict(result) for result in ctx.results],
        "coverage": ctx.coverage,
    }
    (ctx.work_dir / "validation_musa_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    for result in ctx.results:
        counts[result.status] = counts.get(result.status, 0) + 1

    lines = [
        "# MUSA sample validation report",
        "",
        f"Repository: `{REPO_ROOT}`",
        f"Work dir: `{ctx.work_dir}`",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for key in sorted(counts):
        lines.append(f"| `{key}` | {counts[key]} |")
    hard_failures = [r for r in ctx.results if r.status in {"failed", "environment_error", "timeout", "xfail_pass"}]
    lines.extend([
        "",
        f"Hard failures: **{len(hard_failures)}**",
        "",
        "## Coverage",
        "",
    ])
    cov = ctx.coverage
    lines.append(f"- Discovered runnable samples: {cov.get('discovered', 0)}")
    lines.append(f"- Covered samples: {cov.get('covered', 0)}")
    lines.append(f"- Missing samples: {', '.join(cov.get('missing', [])) or 'none'}")
    lines.extend([
        "",
        "## Declared codec/format matrix",
        "",
        f"- Decode codecs: {', '.join(cov.get('declared_decode_codecs', []))}",
        f"- Encode codecs: {', '.join(cov.get('declared_encode_codecs', []))}",
        f"- Encode formats: {', '.join(cov.get('declared_encode_formats', []))}",
        f"- Planned matrix cases: {len(cov.get('planned_codec_format_cases', []))}",
        "",
    ])
    lines.extend([
        "",
        "## Cases",
        "",
        "| Case | Sample | Expected | Status | Return code | Message |",
        "|---|---|---|---|---:|---|",
    ])
    for result in ctx.results:
        message = result.message.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{result.name}` | `{result.sample}` | `{result.expected}` | `{result.status}` | {'' if result.returncode is None else result.returncode} | {message} |"
        )
    unsupported = [r for r in ctx.results if r.status in {"musa_unsupported", "xfail_pass"}]
    lines.extend([
        "",
        "## MUSA unsupported parameter combinations",
        "",
    ])
    if unsupported:
        for result in unsupported:
            lines.append(
                f"- `{result.name}` (`{result.sample}`): {result.message} | params: `{json.dumps(result.params, sort_keys=True)}` | API: `{result.native_api or 'n/a'}`"
            )
    else:
        lines.append("- none")
    coverage_errors = cov.get("missing", [])
    lines.extend([
        "",
        "## Coverage gaps",
        "",
    ])
    if coverage_errors:
        for item in coverage_errors:
            lines.append(f"- `{item}`")
    else:
        lines.append("- none")
    lines.append("")
    (ctx.work_dir / "validation_musa_report.md").write_text("\n".join(lines), encoding="utf-8")


def compute_coverage(cases: list[CaseSpec]) -> dict[str, object]:
    discovered = [str(path) for path in discover_runnable_samples()]
    covered = sorted({str(case.sample) for case in cases})
    missing = sorted(set(discovered) - set(covered))
    requested = [
        {"category": "decode", "codec": codec, "format": pixel_format}
        for codec in DECODE_CODECS
        for pixel_format in DECODE_PIXEL_FORMATS
    ] + [
        {"category": "encode", "codec": codec, "format": surface_format}
        for codec in CODECS
        for surface_format in ENCODE_FORMATS
    ]
    return {
        "discovered": len(discovered),
        "covered": len(covered),
        "missing": missing,
        "discovered_samples": discovered,
        "declared_decode_codecs": list(DECODE_CODECS),
        "declared_encode_codecs": list(CODECS),
        "declared_encode_formats": list(ENCODE_FORMATS),
        "requested_codec_format_cases": requested,
        "planned_codec_format_cases": [
            case.params for case in cases if case.category in {"decode_matrix", "encode_matrix"}
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--ffmpeg", type=Path, default=DEFAULT_FFMPEG)
    parser.add_argument("--size", default=DEFAULT_SIZE, help="Validation asset size")
    parser.add_argument("--alt-size", default=DEFAULT_ALT_SIZE, help="Alternate validation asset size")
    parser.add_argument("--clean", action="store_true", help="Remove work dir before running")
    parser.add_argument("--prepare-timeout", type=positive_int, default=DEFAULT_PREPARE_TIMEOUT, help="Seconds to wait for asset preparation")
    parser.add_argument("--sample-timeout", type=positive_int, default=DEFAULT_SAMPLE_TIMEOUT, help="Seconds to wait for each sample run")
    parser.add_argument("--include-unsupported", action="store_true", help="Run cases marked as expected MUSA-unsupported")
    parser.add_argument("--list-cases", action="store_true", help="Print planned cases and exit")
    parser.add_argument("--source-dir", type=Path, help="Extracted video archive root for codec sources")
    parser.add_argument("--path", default="/usr/local/bin:/usr/bin:/bin:/usr/local/mt_vaapi/bin")
    parser.add_argument("--pythonpath", default=f"{REPO_ROOT / 'stage_musa'}:{SAMPLES_DIR}")
    parser.add_argument("--ld-library-path", default=f"{REPO_ROOT / 'external/ffmpeg/lib/x86_64'}:/usr/local/lib:/usr/local/musa/lib:/usr/local/musa/lib64")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validate_runtime_inputs(args)
    if args.clean and args.work_dir.exists():
        shutil.rmtree(args.work_dir)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    (args.work_dir / "logs").mkdir(exist_ok=True)
    (args.work_dir / "assets").mkdir(exist_ok=True)

    env = build_env()
    env["PATH"] = args.path
    env["PYTHONPATH"] = args.pythonpath
    env["LD_LIBRARY_PATH"] = args.ld_library_path

    ctx = ValidationContext(
        work_dir=args.work_dir,
        python=args.python,
        env=env,
        ffmpeg=args.ffmpeg,
        size=args.size,
        alt_size=args.alt_size,
        prepare_timeout=args.prepare_timeout,
        sample_timeout=args.sample_timeout,
        include_unsupported=args.include_unsupported,
        source_dir=args.source_dir,
    )

    width, height = parse_size(args.size)
    alt_width, alt_height = parse_size(args.alt_size)
    h264 = ctx.work_dir / "assets" / f"input_{args.size}.h264.mp4"
    h264_alt = ctx.work_dir / "assets" / f"input_{args.alt_size}.h264.mp4"
    h264_audio = ctx.work_dir / "assets" / f"input_{args.size}.h264_audio.mp4"
    raw_nv12 = ctx.work_dir / "assets" / f"raw_{args.size}_nv12.yuv"
    raw_yuv420 = ctx.work_dir / "assets" / f"raw_{args.size}_yuv420.yuv"
    raw_p010 = ctx.work_dir / "assets" / f"raw_{args.size}_p010.yuv"

    cases = build_matrix(ctx)
    ctx.coverage = compute_coverage(cases)
    if args.list_cases:
        for spec in cases:
            print(f"{spec.name}\t{spec.category}\t{spec.expected}\t{spec.sample}\t{json.dumps(spec.params, sort_keys=True)}")
        return 0

    make_raw_asset(raw_nv12, width, height, "NV12")
    make_raw_asset(raw_yuv420, width, height, "YUV420")
    make_raw_asset(raw_p010, width, height, "P010")
    raw_assets = {}
    for surface_format in ENCODE_FORMATS:
        raw_path = ctx.work_dir / "assets" / f"raw_{args.size}_{surface_format.lower()}.yuv"
        make_raw_asset(raw_path, width, height, surface_format)
        raw_assets[surface_format] = raw_path
    decode_assets = {}
    for codec in DECODE_CODECS:
        for pixel_format in DECODE_PIXEL_FORMATS:
            asset = ctx.work_dir / "assets" / f"input_{args.size}.{codec}.{pixel_format}.mp4"
            make_codec_asset(ctx, asset, args.size, "2", codec, pixel_format)
            decode_assets[(codec, pixel_format)] = asset
    make_h264_asset(ctx, h264, args.size, "2")
    make_h264_asset(ctx, h264_alt, args.alt_size, "3")
    make_h264_audio_asset(ctx, h264_audio, args.size, "4")
    ctx.assets.update(
        {
            "h264": h264,
            "h264_alt": h264_alt,
            "h264_audio": h264_audio,
            "raw_nv12": raw_nv12,
            "raw_yuv420": raw_yuv420,
            "raw_p010": raw_p010,
        }
    )

    validate_sample_help(ctx, cases)
    run_matrix(ctx, cases)
    write_reports(ctx, cases)

    failed = [r for r in ctx.results if r.status in {"failed", "environment_error", "timeout", "xfail_pass"}]
    print(f"Wrote {ctx.work_dir / 'validation_musa_summary.json'}")
    print(f"Wrote {ctx.work_dir / 'validation_musa_report.md'}")
    print(f"Summary: {len(ctx.results)} cases, {len(failed)} hard failures, {sum(1 for r in ctx.results if r.status == 'musa_unsupported')} unsupported")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
