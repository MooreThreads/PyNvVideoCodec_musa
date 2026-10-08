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

import argparse
import os
import subprocess
import time
import random
import json
import datetime
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
import PyNvVideoCodec as nvc
from typing import Optional, Dict

import threading
from tqdm import tqdm

# FFmpeg subprocess environment: the PyNvVideoCodec process may preload a
# bundled FFmpeg via LD_LIBRARY_PATH, which breaks the system ffmpeg binary
# spawned for video generation/transcoding. Run ffmpeg with a clean env.
FFMPEG_ENV = {k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"}


"""
Benchmark script for comparing segmented video transcoding performance.

This script generates (or reuses) a Mandelbrot set video with FFmpeg and benchmarks
transcoding performance using multiple approaches: PyNvVideoCodec and various FFmpeg
configurations. It supports parallel processing with multiple threads.

Features:
- Supports multiple video codecs (H.264, HEVC, AV1)
- Tests different thread counts for parallel processing
- Generates performance comparison results
- Saves results in JSON format with execution logs
- Automatically reuses previously generated videos

NOTE 1: Videos are generated using FFmpeg only for the first run. Subsequent runs will
reuse existing videos if they match the parameters (codec, resolution, duration, etc.).

NOTE 2: Generated videos are stored in the source_videos/ directory with names that
include codec and resolution information.

NOTE 3: The script will run transcoding in multiple threads if specified. Number of
threads is controlled by the --numthreads argument.

NOTE 4: Execution logs are automatically saved to track all steps including video
generation/reuse, segment creation, and transcoding results. Default location is
logs/run_{timestamp}.json (e.g., logs/run_20240615_123045.json). These logs can be
replayed using the --replay flag to re-run transcoding with the same parameters.

Parameters:
    -g, --gpuid (int): GPU device ID to use (default: 0)
    -W, --width (int): Width of the video in pixels (default: 1920)
    -H, --height (int): Height of the video in pixels (default: 1080)
    -d, --duration (int): Duration of the video in seconds (default: 10)
    -fps, --fps (int): Frames per second (default: 30)
    -p, --preset (str): Encoder preset P1-P7 (default: P4)
    -ic, --input-codec (str): Input codec for video generation: h264, hevc, av1 (default: h264)
    -c, --codec (str): Output codec for transcoding: h264, hevc, av1 (default: h264)
    -ibf, --input-bframes (int): Number of B-frames for input video generation (default: 2)
    -bf, --bframes (int): Number of B-frames for output transcoding (default: 0)
    -n, --numthreads (int): Number of concurrent threads for parallel processing (default: 1)
    -s, --segments (int): Number of random segments to create (default: 3)
    -u, --usage (list[int]): Transcoding modes to benchmark (default: [0, 1, 2, 3])
        See "Transcoding Modes" section below for detailed explanation.
    --chunk-size (int): Number of segments per FFmpeg batch command (default: 5)
    --segment-duration (int): Minimum duration of each segment in seconds (default: 1)
    --gop-size (int): GOP size for video encoding (default: 250)
    --log (str): Path to save execution log (default: logs/run_{timestamp}.json)
    --random-seed (int): Random seed for reproducible segment generation (optional)
    -i, --input (str): Use existing video file instead of generating new one (optional)
    --replay (str): Replay transcoding from a previous log file (optional)

Transcoding Modes:
    The script benchmarks 4 different approaches to segmented video transcoding:

    Mode 0 - PyNVC Transcoding:
        Uses PyNvVideoCodec's Transcoder class with segmented_transcode() method.
        - One output file per segment
        - GPU-accelerated decode and encode pipeline
        - Output: pynvc_out/{base}_{codec}_{resolution}_bf{bframes}_transcoded_{start}_{end}.mp4
          Example: pynvc_out/mandelbrot_h264_1920x1080_bf0_transcoded_1.75_5.74.mp4

    Mode 1 - FFmpeg Without Map (Sequential Processing):
        Uses FFmpeg with separate commands for each segment.
        - Individual FFmpeg process per segment (-ss/-to for time ranges)
        - Hardware-accelerated decode (cuvid) and encode (nvenc)
        - Simple approach but spawns multiple processes
        - Output: ffmpeg_out/{base}_{codec}_{resolution}_bf{bframes}_{start}_{end}.mp4
          Example: ffmpeg_out/mandelbrot_h264_1920x1080_bf0_1.75_5.74.mp4
        Command example:
            ffmpeg -ss START -to END -c:v h264_cuvid -i INPUT \
                   -c:v h264_nvenc -c:a copy OUTPUT

    Mode 2 - FFmpeg With Map (No Audio, Batch Processing):
        Uses FFmpeg's filter_complex to process multiple segments in one command.
        - Single FFmpeg process handles multiple segments simultaneously
        - Hardware-accelerated with CUDA
        - Uses trim filters for precise segment extraction
        - Video only (no audio processing)
        - Output: ffmpeg_fc_out/{base}_{codec}_{resolution}_bf{bframes}_{start}_{end}.mp4
          Example: ffmpeg_fc_out/mandelbrot_h264_1920x1080_bf0_1.75_5.74.mp4
        Command example:
            ffmpeg -hwaccel cuda -c:v h264_cuvid -i INPUT \
                   -filter_complex "[0:v]trim=start=S1:end=E1[v0];..." \
                   -map [v0] -c:v h264_nvenc -an OUT1 \
                   -map [v1] -c:v h264_nvenc -an OUT2

    Mode 3 - FFmpeg With Map (With Audio, Batch Processing):
        Enhanced version of Mode 2 with audio support.
        - Single FFmpeg process for multiple segments
        - Processes both video (trim) and audio (atrim) streams
        - Hardware-accelerated video processing
        - Full quality audio transcoding (AAC)
        - Most complete but potentially slower due to audio processing
        - Output: ffmpeg_fc_out/{base}_{codec}_{resolution}_bf{bframes}_{start}_{end}.mp4
          Example: ffmpeg_fc_out/mandelbrot_h264_1920x1080_bf0_1.75_5.74.mp4
        Command example:
            ffmpeg -hwaccel cuda -c:v h264_cuvid -i INPUT \
                   -filter_complex "[0:v]trim=start=S1:end=E1[v0]; \
                                    [0:a]atrim=start=S1:end=E1[a0];..." \
                   -map [v0] -map [a0] -c:v h264_nvenc -c:a aac OUT1 \
                   -map [v1] -map [a1] -c:v h264_nvenc -c:a aac OUT2

Returns:
    None. Results are printed to console and saved to log file.

Logging:
    The script automatically logs all execution steps to a JSON file for tracking and replay:

    Log Structure:
    - timestamp: ISO format timestamp of when the script was run
    - args: All command-line arguments used
    - steps: Detailed list of execution steps:
        * video_generation: When a new video is generated
        * video_reuse: When an existing video is reused
        * video_input: When user provides input video with -i flag
        * segment_creation: Random segments generated for transcoding
        * transcoding: Each transcoding operation with its parameters
        * summary: Final results with performance metrics
    - results: Performance comparison data (time, throughput, FPS)

    Default Log Location:
    - Normal runs: logs/run_{timestamp}.json
    - Replay runs: logs/replay_{timestamp}.json
    - Custom path: Specify with --log argument

    All logs are stored in the logs/ directory (automatically created if not present).

Output Files:
    - Transcoded video segments (one file per segment):
        * pynvc_out/{base}_{codec}_{resolution}_bf{bframes}_transcoded.mp4
        * ffmpeg_out/{base}_{codec}_{resolution}_bf{bframes}_{start}_{end}.mp4
        * ffmpeg_fc_out/{base}_{codec}_{resolution}_bf{bframes}_{start}_{end}.mp4
    - Source videos: source_videos/mandelbrot_{codec}_{resolution}.mp4

    Where:
        {base} = base filename (e.g., mandelbrot)
        {codec} = output codec (h264, hevc, av1)
        {resolution} = video resolution (e.g., 1920x1080)
        {bframes} = number of B-frames
        {start}_{end} = segment timestamps (e.g., 1.75_5.74)

Examples:
    Basic usage with default parameters (runs all 4 modes):
    >>> python segmented_transcode_benchmark.py

    Compare only PyNVC vs FFmpeg with audio:
    >>> python segmented_transcode_benchmark.py -u 0 3

    Test only PyNVC transcoding:
    >>> python segmented_transcode_benchmark.py -u 0

    Compare all FFmpeg modes (without PyNVC):
    >>> python segmented_transcode_benchmark.py -u 1 2 3

    Custom video parameters with specific mode:
    >>> python segmented_transcode_benchmark.py -W 1920 -H 1080 -d 30 -fps 30 -p P4 -c h264 -n 4 -s 10 -u 0

    Using HEVC codec with B-frames:
    >>> python segmented_transcode_benchmark.py -ic hevc -c hevc -ibf 2 -bf 2

    Save log to custom location:
    >>> python segmented_transcode_benchmark.py --log my_benchmark_results.json

    Replay from previous log:
    >>> python segmented_transcode_benchmark.py --replay logs/run_20240615_123045.json
"""

# Global log file handle
log_file = None
log_data = {
    "timestamp": "",
    "args": {},
    "steps": [],
    "results": {}
}

def parse_ffmpeg_progress(line: str) -> Optional[Dict[str, str]]:
    """Parse FFmpeg progress line and extract key information"""
    if not line.strip():
        return None

    progress_data = {}

    if '=' in line:
        for item in line.split():
            if '=' in item:
                key, value = item.split('=', 1)
                progress_data[key] = value

    return progress_data if progress_data else None


FFMPEG_ENCODERS = {
    'cuda': {
        'h264': 'h264_nvenc',
        'hevc': 'hevc_nvenc',
        'av1': 'av1_nvenc',
    },
    'musa': {
        'h264': 'h264_mtenc',
        'hevc': 'hevc_mtenc',
        'av1': 'av1_mtenc',
    },
}

def current_backend() -> str:
    return getattr(nvc, '__backend__', 'cuda')


def resolve_ffmpeg_encoder(codec: str, backend: str) -> str:
    try:
        return FFMPEG_ENCODERS[backend.lower()][codec.lower()]
    except KeyError as exc:
        raise ValueError(f'Unsupported ffmpeg backend/codec combination: {backend}/{codec}') from exc


def resolve_ffmpeg_decoder(codec: str, backend: str) -> Optional[str]:
    if backend.lower() != 'cuda':
        return None
    return {
        'h264': 'h264_cuvid',
        'avc': 'h264_cuvid',
        'hevc': 'hevc_cuvid',
        'av1': 'av1_cuvid',
    }.get(codec.lower())


def resolve_ffmpeg_hwaccel_args(backend: str) -> list[str]:
    if backend.lower() == 'cuda':
        return ['-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda']
    return []


def log_step(step_type, description, params=None, results=None):
    """
    Log a step to both console and log file

    Parameters:
        step_type (str): Type of step (video_generation, segment_creation, transcoding)
        description (str): Human-readable description
        params (dict): Parameters used for this step
        results (dict): Results from this step
    """
    global log_file, log_data

    step = {
        "type": step_type,
        "description": description,
        "timestamp": datetime.datetime.now().isoformat(),
        "params": params or {},
        "results": results or {}
    }

    # Add to log data
    log_data["steps"].append(step)

    # Print to console
    print(f"[LOG] {description}")

    # Write to log file if open
    if log_file:
        # Update the file with the latest log data
        log_file.seek(0)
        json.dump(log_data, log_file, indent=2)
        log_file.truncate()
        log_file.flush()


def generate_mandelbrot_video(width, height, duration, fps, output_path, gop_size, input_codec="h264", input_bframes=2,
                              ffmpeg_path="ffmpeg", encoder=None):
    """
    Generate a Mandelbrot set zoom video with audio using FFmpeg

    Uses optimized approach: generates a short base clip and loops it for better
    performance with long duration videos.

    Parameters:
        width (int): Video width
        height (int): Video height
        duration (int): Video duration in seconds
        fps (int): Frames per second
        output_path (str): Path to save the generated video
        gop_size (int): GOP size for encoding
        input_codec (str): Codec to use for video generation (h264, hevc, av1)
        input_bframes (int): Number of B-frames for video generation

    Returns:
        str: Path to the generated video
    """
    encoder = encoder or resolve_ffmpeg_encoder(input_codec, current_backend())

    # Update output path to include codec information
    base, ext = os.path.splitext(output_path)
    codec_output_path = f"{base}_{input_codec}_{width}x{height}_{duration}s_{fps}fps_gop{gop_size}_bf{input_bframes}{ext}"
    # Log the step
    log_step("video_generation", f"Generating Mandelbrot video ({width}x{height}, {duration}s, {fps} fps, {input_codec}, B-frames: {input_bframes})",
             params={"width": width, "height": height, "duration": duration, "fps": fps,
                    "output_path": codec_output_path, "gop_size": gop_size, "codec": input_codec, "bframes": input_bframes})

    print(f"Generating Mandelbrot set video with audio at {width}x{height}, {duration}s duration, {fps} fps")
    print(f"Using FFmpeg binary: {ffmpeg_path}")
    print(f"Using codec: {input_codec}, encoder: {encoder}, B-frames: {input_bframes}")

    # Create the directory if it doesn't exist
    os.makedirs(os.path.dirname(codec_output_path) or '.', exist_ok=True)

    print(f"Using GOP size: {gop_size} and {input_bframes} B-frames")

    # Determine base clip duration (use min of 10 seconds or full duration)
    base_duration = min(10, duration)
    temp_clip = f"{base}_temp_{input_codec}_{width}x{height}_{duration}s_{fps}fps_gop{gop_size}_bf{input_bframes}{ext}"

    # Step 1: Generate short Mandelbrot base clip if it doesn't exist
    if not os.path.exists(temp_clip):
        print(f"\nStep 1: Generating {base_duration}s Mandelbrot base clip...")
        print("This base clip will be reused for future runs with same parameters")


        # FFmpeg command to generate base Mandelbrot clip
        cmd_base = [
            ffmpeg_path, "-y",
            "-progress", "pipe:2",
            "-v", "warning",
            # Video input from mandelbrot filter
            "-f", "lavfi",
            "-i", f"mandelbrot=size={width}x{height}:rate={fps}:start_scale=3:end_scale=0.1",
            # Audio input - sine wave
            "-f", "lavfi",
            "-i", f"sine=frequency=220:sample_rate=44100:duration={base_duration}",
            # Set duration
            "-t", str(base_duration),
            # Video encoding with specified codec
            *( ["-pix_fmt", "nv12"] if encoder.endswith("_mtenc") else [] ),
            "-c:v", encoder,
            "-preset", "medium",
            "-g", str(gop_size),
            "-bf", str(input_bframes),
            # Audio encoding
            "-c:a", "aac",
            "-b:a", "128k",
            # Output
            temp_clip
        ]

        try:
            # Calculate estimated total frames for progress tracking
            estimated_frames = base_duration * fps

            # Execute FFmpeg command with progress tracking
            print(f"Generating base clip ({base_duration}s)...")
            process = subprocess.Popen(cmd_base, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=FFMPEG_ENV,
                                     universal_newlines=True, bufsize=1)

            # Progress bar setup
            pbar = tqdm(total=estimated_frames, unit='frames',
                       desc=f"Base clip generation",
                       ncols=80, leave=True)

            # Read stderr line by line to get progress
            current_frame = 0
            max_frame_seen = 0
            last_update_time = time.time()
            update_interval = 0.5

            while True:
                line = process.stderr.readline()
                if not line:
                    break

                # Parse progress information
                progress_data = parse_ffmpeg_progress(line.strip())
                if progress_data and 'frame' in progress_data:
                    try:
                        frame_num = int(progress_data['frame'])
                        max_frame_seen = max(max_frame_seen, frame_num)

                        current_time = time.time()
                        if (current_time - last_update_time >= update_interval or
                            frame_num - current_frame >= 10):

                            if frame_num > estimated_frames:
                                pbar.total = frame_num + 50

                            if frame_num > current_frame:
                                pbar.update(frame_num - current_frame)
                                current_frame = frame_num
                                last_update_time = current_time

                    except (ValueError, KeyError):
                        continue

            # Wait for process to complete
            process.wait()

            # Ensure progress bar reaches 100%
            if max_frame_seen > current_frame:
                pbar.update(max_frame_seen - current_frame)
                current_frame = max_frame_seen

            if current_frame < pbar.total:
                pbar.update(pbar.total - current_frame)

            pbar.close()

            if process.returncode != 0:
                remaining_stderr = process.stderr.read()
                print(f"Error generating base clip: {remaining_stderr}")
                raise subprocess.CalledProcessError(process.returncode, cmd_base, remaining_stderr)

            print(f"✓ Base clip generated: {temp_clip} ({max_frame_seen} frames)")

        except subprocess.CalledProcessError as e:
            print(f"FFmpeg error: {e}")
            raise
        except Exception as e:
            print(f"Error: {e}")
            raise
    else:
        print(f"✓ Reusing existing base clip: {temp_clip}")

    # Step 2: Loop the base clip to desired duration (if needed)
    if duration > base_duration:
        print(f"\nStep 2: Looping base clip to {duration}s duration...")
        loop_count = int(duration / base_duration) + 1
        print(f"Looping {loop_count} times to reach target duration")

        # FFmpeg command to loop the video
        cmd_loop = [
            ffmpeg_path, "-y",
            "-progress", "pipe:2",
            "-v", "warning",
            "-stream_loop", str(loop_count),
            "-i", temp_clip,
            "-t", str(duration),
            # Re-encode with same parameters
            *( ["-pix_fmt", "nv12"] if encoder.endswith("_mtenc") else [] ),
            "-c:v", encoder,
            "-preset", "fast",  # Use faster preset for looping
            "-g", str(gop_size),
            "-bf", str(input_bframes),
            "-c:a", "aac",
            "-b:a", "128k",
            codec_output_path
        ]

        try:
            # Calculate estimated total frames for progress tracking
            estimated_frames = duration * fps

            # Execute FFmpeg command with progress tracking
            process = subprocess.Popen(cmd_loop, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=FFMPEG_ENV,
                                     universal_newlines=True, bufsize=1)

            # Progress bar setup
            video_name = os.path.basename(codec_output_path)
            pbar = tqdm(total=estimated_frames, unit='frames',
                       desc=f"Looping to {duration}s",
                       ncols=80, leave=True)

            # Read stderr line by line to get progress
            current_frame = 0
            max_frame_seen = 0
            last_update_time = time.time()
            update_interval = 0.5

            while True:
                line = process.stderr.readline()
                if not line:
                    break

                # Parse progress information
                progress_data = parse_ffmpeg_progress(line.strip())
                if progress_data and 'frame' in progress_data:
                    try:
                        frame_num = int(progress_data['frame'])
                        max_frame_seen = max(max_frame_seen, frame_num)

                        current_time = time.time()
                        if (current_time - last_update_time >= update_interval or
                            frame_num - current_frame >= 10):

                            if frame_num > estimated_frames:
                                pbar.total = frame_num + 50

                            if frame_num > current_frame:
                                pbar.update(frame_num - current_frame)
                                current_frame = frame_num
                                last_update_time = current_time

                    except (ValueError, KeyError):
                        continue

            # Wait for process to complete
            process.wait()

            # Ensure progress bar reaches 100%
            if max_frame_seen > current_frame:
                pbar.update(max_frame_seen - current_frame)
                current_frame = max_frame_seen

            if current_frame < pbar.total:
                pbar.update(pbar.total - current_frame)

            pbar.close()

            if process.returncode != 0:
                remaining_stderr = process.stderr.read()
                print(f"Error looping video: {remaining_stderr}")
                raise subprocess.CalledProcessError(process.returncode, cmd_loop, remaining_stderr)

            print(f"✓ Video generation with audio complete: {codec_output_path}")
            print(f"  Video codec: {encoder} with {gop_size} GOP size and {input_bframes} B-frames")
            print(f"  Frames encoded: {max_frame_seen}")
            print(f"  Performance: Generated {duration}s video by looping {base_duration}s base clip")

            # Clean up temp clip since we have the looped video
            if os.path.exists(temp_clip):
                os.remove(temp_clip)
                print(f"  Cleaned up temp clip: {temp_clip}")

            return codec_output_path

        except subprocess.CalledProcessError as e:
            print(f"FFmpeg error: {e}")
            raise
        except Exception as e:
            print(f"Error: {e}")
            raise
    else:
        # Duration is <= base_duration, just rename/copy the temp clip
        print(f"\nUsing base clip as final output (duration <= {base_duration}s)")
        if os.path.exists(codec_output_path):
            os.remove(codec_output_path)
        os.rename(temp_clip, codec_output_path)
        print(f"✓ Video generation complete: {codec_output_path}")
        return codec_output_path


def generate_random_segments(duration, num_segments, min_segment_duration=1.0):
    """
    Generate random non-overlapping start and end timestamps for video segments

    Parameters:
        duration (float): Total video duration in seconds
        num_segments (int): Number of segments to generate
        min_segment_duration (float): Minimum duration of each segment in seconds

    Returns:
        list: List of tuples containing (start_time, end_time) for each segment
    """
    segments = []

    # Make sure we can fit all segments with minimum duration
    total_segment_time = num_segments * min_segment_duration
    if total_segment_time > duration:
        num_segments = int(duration / min_segment_duration)
        print(f"Warning: Reduced number of segments to {num_segments} to ensure minimum segment duration")
        total_segment_time = num_segments * min_segment_duration

    if num_segments == 0:
        print("Warning: Cannot create any segments with the given parameters")
        return []

    # Calculate the total available gap time (time not occupied by segments)
    total_gap_time = duration - total_segment_time

    # Divide video into num_segments equal slots and place one segment randomly in each
    # This guarantees we always get exactly num_segments segments
    slot_duration = duration / num_segments

    # Calculate max segment duration (allow some variation but cap it)
    max_segment_duration = min(slot_duration * 0.9, min_segment_duration * 2)
    max_segment_duration = max(max_segment_duration, min_segment_duration)  # Ensure max >= min

    for i in range(num_segments):
        slot_start = i * slot_duration
        slot_end = (i + 1) * slot_duration

        # Randomize segment duration between min and max
        segment_duration = random.uniform(min_segment_duration, max_segment_duration)

        # Ensure segment fits within the slot
        if segment_duration > slot_duration:
            segment_duration = slot_duration

        # Calculate the range where segment can start within this slot
        max_start = slot_end - segment_duration
        if max_start < slot_start:
            max_start = slot_start
            segment_duration = slot_end - slot_start  # Adjust duration to fit

        # Random start position within the valid range
        start_time = random.uniform(slot_start, max_start)
        end_time = start_time + segment_duration

        # Ensure we don't exceed video duration
        if end_time > duration:
            end_time = duration
            start_time = max(0, end_time - segment_duration)

        segments.append((start_time, end_time))

    # Sort segments by start time
    segments.sort()

    return segments


def run_subprocess(cmd, shell=False, description=""):
    """
    Run a subprocess and wait for completion, with proper error handling

    Parameters:
        cmd: Command to run (list or string)
        shell: Whether to use shell execution
        description: Description of the process for logging

    Returns:
        tuple: (stdout, stderr) from the process
    """
    try:
        print(f"Starting {description}...")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, shell=shell, env=FFMPEG_ENV)

        # Wait for the process to complete
        stdout, stderr = process.communicate()

        # Check if process completed successfully
        if process.returncode != 0:
            print(f"Error in {description}: {stderr}")
            print(f"Command was: {cmd}")
        else:
            print(f"{description} completed successfully")

        return stdout, stderr
    except Exception as e:
        print(f"Exception in {description}: {e}")
        raise


def segmented_transcode(args):
    """
    Transcode the input video using the specified method

    Parameters:
        args (list): List of parameters including video path, clip_start_end, config, usage, etc.
    """
    print(f"Segmented transcode for {args}")
    video_path, clip_start_end, config, fps, usage, chunk_size = args
    print(f"Segmented transcode for {video_path}")
    print(f"Number of segments: {len(clip_start_end)}")
    print(f"Using mode: {usage}")

    # Get B-frames setting from config
    bframes = config.get("bf", 0)  # Default to 0 if not specified
    print(f"Using {bframes} B-frames for transcoding")

    # Properly extract base filename without extension
    base, _ = os.path.splitext(os.path.basename(video_path))

    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(os.path.abspath(video_path)), exist_ok=True)

    # Start timing
    start_time = time.time()

    # Get codec and resolution from config
    codec = config.get("codec", "h264")
    width = config.get("width", 1920)
    height = config.get("height", 1080)
    resolution = f"{width}x{height}"

    # Create a resolution-codec-bframes suffix for file names
    suffix = f"_{codec}_{resolution}_bf{bframes}"

    backend = config.get('backend', current_backend())
    ffmpeg_path = config.get('ffmpeg_path', 'ffmpeg')
    encoder = config.get('ffmpeg_encoder') or resolve_ffmpeg_encoder(codec, backend)

    # Determine input video codec and decoder to use
    # First try to get from input file using ffprobe
    input_codec = "h264"  # Default assumption
    try:
        probe_cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "stream=codec_name", "-of", "csv=p=0", video_path]
        probe_result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=FFMPEG_ENV)
        if probe_result.returncode == 0 and probe_result.stdout.strip():
            input_codec = probe_result.stdout.strip().lower()
            print(f"Detected input codec: {input_codec}")
    except Exception as e:
        print(f"Error detecting input codec: {str(e)}. Using default h264 decoder.")

    decoder = resolve_ffmpeg_decoder(input_codec, backend)
    hwaccel_args = resolve_ffmpeg_hwaccel_args(backend)
    print(f"Using decoder: {decoder if decoder else 'software default'}")
    print(f"Using FFmpeg backend: {backend}")
    print(f"Using FFmpeg binary: {ffmpeg_path}")

    # Create output directories if they don't exist
    os.makedirs("pynvc_out", exist_ok=True)
    os.makedirs("ffmpeg_out", exist_ok=True)
    os.makedirs("ffmpeg_fc_out", exist_ok=True)

    try:
        if usage == 0:
            # PyNVC Usage
            out_file_path = os.path.join("pynvc_out", f"{base}{suffix}_transcoded.mp4")
            print(f"Output will be saved to: ./pynvc_out/")

            # Make a copy of the config and remove non-Transcoder kwargs
            transcoder_config = config.copy()
            for key in ('width', 'height', 'ffmpeg_path', 'backend', 'ffmpeg_encoder'):
                transcoder_config.pop(key, None)

            # Pass the modified config to the Transcoder
            tr = nvc.Transcoder(video_path, out_file_path, 0, 0, 0, **transcoder_config)
            for start, end in clip_start_end:
                tr.segmented_transcode(start, end)

        elif usage == 1:
            print(f"FFmpeg without map")
            print(f"Output files will be saved to: ./ffmpeg_out/")
            for i in range(0, len(clip_start_end), chunk_size):
                chunk = clip_start_end[i:i+chunk_size]
                for start, end in chunk:
                    # Include codec and resolution in output file path
                    out_file_path = f"./ffmpeg_out/{base}{suffix}_{start:.2f}_{end:.2f}.mp4"
                    decoder_cmd = f" -c:v {decoder}" if decoder else ""
                    ff = (f" {ffmpeg_path} -loglevel warning -hide_banner -y "
                            f"{decoder_cmd}"
                            f" -ss {str(start)} "
                            f" -to {str(end)} "
                            f" -i {video_path} "
                            f" -bf {bframes}"  # Use B-frames from config
                            f" -c:v {encoder} "  # Use the correct encoder based on output codec
                            " -c:a copy "
                            f"{out_file_path}")

                    desc = f"FFmpeg transcode segment {start:.2f}s - {end:.2f}s"
                    run_subprocess(ff, shell=True, description=desc)

        elif usage == 2:
            print(f"FFmpeg with map but no audio")
            print(f"Output files will be saved to: ./ffmpeg_fc_out/")
            for i in range(0, len(clip_start_end), chunk_size):
                chunk = clip_start_end[i:i+chunk_size]

                segment_cmd = [ffmpeg_path, "-loglevel", "warning", "-hide_banner", "-y"]
                segment_cmd.extend(hwaccel_args)
                if decoder:
                    segment_cmd.extend(["-c:v", decoder])
                segment_cmd.extend(["-i", video_path])

                filter_complex = []
                map_cmds = []
                output_files = []

                for j, (start, end) in enumerate(chunk):
                    # Include codec and resolution in output file path
                    out_file_path = f"./ffmpeg_fc_out/{base}{suffix}_{start:.2f}_{end:.2f}.mp4"
                    output_files.append(out_file_path)

                    # Add video filter
                    filter_complex.append(f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{j}]")
                    map_cmds.extend(["-map", f"[v{j}]", "-c:v", encoder, "-an", out_file_path])

                # Combine all filters
                segment_cmd.extend(["-filter_complex", ";".join(filter_complex)])
                segment_cmd.extend(map_cmds)

                # Convert the list to a shell command string
                cmd_str = " ".join([
                    f'"{arg}"' if (" " in arg or ";" in arg or "[" in arg) else arg
                    for arg in segment_cmd
                ])

                # Execute FFmpeg command
                desc = f"FFmpeg batch transcode {len(chunk)} segments (no audio)"
                run_subprocess(cmd_str, shell=True, description=desc)

        elif usage == 3:
            print(f"FFmpeg with map and audio")
            print(f"Output files will be saved to: ./ffmpeg_fc_out/")
            for i in range(0, len(clip_start_end), chunk_size):
                chunk = clip_start_end[i:i+chunk_size]

                segment_cmd = [ffmpeg_path, "-y", "-loglevel", "warning"]
                segment_cmd.extend(hwaccel_args)
                if decoder:
                    segment_cmd.extend(["-c:v", decoder])
                segment_cmd.extend(["-i", video_path])

                filter_complex = []
                map_cmds = []
                output_files = []

                for j, (start, end) in enumerate(chunk):
                    # Include codec and resolution in output file path
                    out_file_path = f"./ffmpeg_fc_out/{base}{suffix}_{start:.2f}_{end:.2f}.mp4"
                    output_files.append(out_file_path)

                    # Modify filters to include accurate timing
                    filter_complex.append(f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{j}]")

                    # Check if the video has audio
                    if os.path.exists(video_path):
                        probe_cmd = ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", video_path]
                        probe_result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=FFMPEG_ENV)
                        has_audio = "audio" in probe_result.stdout

                        if has_audio:
                            filter_complex.append(f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{j}]")
                            map_cmds.extend(["-map", f"[v{j}]", "-map", f"[a{j}]"])
                        else:
                            map_cmds.extend(["-map", f"[v{j}]"])
                    else:
                        map_cmds.extend(["-map", f"[v{j}]"])

                    # Convert P4 to p4 (lowercase) for FFmpeg preset
                    ffmpeg_preset = config.get("preset", "p4").lower()

                    # Add encoding parameters
                    map_cmds.extend(["-c:v", encoder])
                    if encoder.endswith('_mtenc'):
                        map_cmds.extend([
                            "-rc", "vbr",
                            "-b:v", "5M",
                            "-maxrate", "10M",
                            "-bufsize", "10M",
                        ])
                    else:
                        map_cmds.extend([
                            "-preset", ffmpeg_preset,
                            "-rc", "vbr",
                            "-b:v", "5M",
                            "-maxrate", "10M",
                            "-bufsize", "10M",
                        ])

                    # Add audio encoding if we have audio
                    audio_filter = f"a{j}" in "".join(filter_complex)
                    if audio_filter:
                        map_cmds.extend(["-c:a", "aac", "-b:a", "192k"])

                    map_cmds.append(out_file_path)

                # Combine all filters
                segment_cmd.extend(["-filter_complex", ";".join(filter_complex)])
                segment_cmd.extend(map_cmds)

                # Convert the list to a shell command string
                cmd_str = " ".join([
                    f'"{arg}"' if (" " in arg or ";" in arg or "[" in arg) else arg
                    for arg in segment_cmd
                ])

                # Execute FFmpeg command
                desc = f"FFmpeg batch transcode {len(chunk)} segments (with audio)"
                run_subprocess(cmd_str, shell=True, description=desc)

        else:
            print(f"Error: Invalid usage mode {usage}. Must be 0, 1, 2, or 3")

    except Exception as e:
        print(f"Error processing {video_path}: {str(e)}")
        raise


def extract_segments_from_log(log_data):
    """
    Extract segment information from log data

    Parameters:
        log_data (dict): Log data from a previous run

    Returns:
        list: List of (start_time, end_time) tuples
    """
    try:
        # Find segment creation step
        for step in log_data.get("steps", []):
            if step.get("type") == "segment_creation":
                if "results" in step and "segments" in step["results"]:
                    segments = step["results"]["segments"]
                    return [(segment["start"], segment["end"]) for segment in segments]

        return []

    except Exception as e:
        print(f"Error parsing segments from log: {e}")
        return []


def replay_from_log(log_path):
    """
    Replay a previous run from a log file

    Parameters:
        log_path (str): Path to the log file
    """
    import re
    global log_data

    print(f"Replaying from log: {log_path}")

    try:
        with open(log_path, 'r') as f:
            log_data = json.load(f)

        print(f"Log timestamp: {log_data['timestamp']}")
        print(f"Original arguments: {json.dumps(log_data['args'], indent=2)}")

        # Extract video path from video generation, video reuse, or video input step
        video_path = None
        video_params = None
        for step in log_data['steps']:
            if step['type'] == 'video_generation':
                video_path = step['params']['output_path']
                video_params = step['params']
                break
            elif step['type'] == 'video_reuse':
                # For video_reuse, the path is in the description or params
                if 'output_path' in step['params']:
                    video_path = step['params']['output_path']
                    video_params = step['params']
                elif 'params' in step and step['params']:
                    # Construct the path from parameters
                    width = step['params'].get('width')
                    height = step['params'].get('height')
                    codec = step['params'].get('codec', 'h264')
                    video_path = f"source_videos/mandelbrot_{codec}_{width}x{height}.mp4"
                    video_params = step['params']
                # Try to extract from description as fallback
                if not video_path and 'description' in step:
                    match = re.search(r'Reusing existing video: (.+)', step['description'])
                    if match:
                        video_path = match.group(1)
                        video_params = step['params']
                break
            elif step['type'] == 'video_input':
                # User provided an input video
                if 'input_path' in step['params']:
                    video_path = step['params']['input_path']
                    video_params = step['params']
                # Try to extract from description as fallback
                if not video_path and 'description' in step:
                    match = re.search(r'Using user-provided input video: (.+)', step['description'])
                    if match:
                        video_path = match.group(1)
                        video_params = step['params']
                break

        if not video_path:
            print("Error: No video generation, video reuse, or video input step found in log")
            print("Available step types:", [step.get('type') for step in log_data.get('steps', [])])
            return

        # Check if the video exists
        if not os.path.exists(video_path):
            print(f"Video file not found: {video_path}")
            print("Regenerating video...")

            # Use video_params if available, otherwise try to get from log_data args
            if video_params:
                video_path = generate_mandelbrot_video(
                    video_params.get('width'),
                    video_params.get('height'),
                    video_params.get('duration'),
                    video_params.get('fps'),
                    video_path,  # Use the constructed path
                    video_params.get('gop_size'),
                    video_params.get('codec', 'h264'),
                    video_params.get('bframes', 2),
                    ffmpeg_path=log_data.get('args', {}).get('ffmpeg', 'ffmpeg'),
                    encoder=resolve_ffmpeg_encoder(video_params.get('codec', 'h264'), log_data.get('args', {}).get('ffmpeg_backend', 'cuda'))
                )
            else:
                # Fallback to args
                args_data = log_data.get('args', {})
                video_path = generate_mandelbrot_video(
                    args_data.get('width', 1920),
                    args_data.get('height', 1080),
                    args_data.get('duration', 10),
                    args_data.get('fps', 30),
                    video_path,
                    args_data.get('gop_size', 250),
                    args_data.get('input_codec', 'h264'),
                    args_data.get('input_bframes', 2),
                    ffmpeg_path=args_data.get('ffmpeg', 'ffmpeg'),
                    encoder=resolve_ffmpeg_encoder(args_data.get('input_codec', 'h264'), args_data.get('ffmpeg_backend', 'cuda'))
                )
        else:
            print(f"Using existing video: {video_path}")

        # Extract segments
        clip_start_end = extract_segments_from_log(log_data)
        if not clip_start_end:
            print("Error: No segments found in log")
            return

        # Extract usage modes
        usage_modes = []
        for step in log_data['steps']:
            if step['type'] == 'transcoding' and 'usage' in step['params']:
                if step['params']['usage'] not in usage_modes:
                    usage_modes.append(step['params']['usage'])

        if not usage_modes:
            print("Error: No transcoding steps found in log")
            return

        print(f"Replay will use these usage modes: {usage_modes}")

        # Extract config
        config = log_data['args'].get('config', {"preset": "P4", "codec": "h264", "tuning_info": "high_quality", "bf": "0"})

        # Calculate total frames
        fps = log_data['args'].get('fps', 30)
        segment_frames = sum((end - start) * fps for start, end in clip_start_end)

        # Store results for comparison
        results = {}

        # Run transcoding for each usage mode
        for usage in usage_modes:
            if usage not in [0, 1, 2, 3]:
                print(f"Warning: Invalid usage mode {usage}. Skipping...")
                continue

            print("\n" + "=" * 80)
            print(f"REPLAY: TRANSCODING SEGMENTS USING MODE {usage}")
            print("=" * 80)

            # Get mode description
            mode_desc = {
                0: "PyNVC transcoding",
                1: "FFmpeg without map",
                2: "FFmpeg with map (no audio)",
                3: "FFmpeg with map (with audio)"
            }.get(usage, "Unknown mode")

            print(f"Running: {mode_desc}")

            futures_list = []
            starttime = time.time()

            # Extract numthreads and chunk_size
            numthreads = log_data['args'].get('numthreads', 1)
            chunk_size = log_data['args'].get('chunk_size', 5)

            with ThreadPoolExecutor(max_workers=numthreads) as executor:
                # Submit task to thread pool
                futures = [executor.submit(segmented_transcode, [
                    video_path,
                    clip_start_end,
                    config,
                    fps,
                    usage,
                    chunk_size
                ])]
                futures_list.append(futures)

                # Wait for all tasks to complete and propagate worker failures.
                for future in futures_list:
                    wait(future)
                    for item in future:
                        item.result()

            endtime = time.time()
            total_time = endtime - starttime
            throughput = segment_frames / total_time if total_time > 0 else 0

            # Store results
            results[usage] = {
                'mode': mode_desc,
                'time': total_time,
                'throughput': throughput
            }

            print(f"Completed {mode_desc}")
            print(f"Processing time: {total_time:.2f} seconds")
            print(f"Throughput: {throughput:.2f} frames/second")

            # Log the results
            log_step("replay_results", f"Replay results for mode {usage}",
                    params={"usage": usage, "mode": mode_desc},
                    results={"time": total_time, "throughput": throughput})

        # Print comparison results with additional details
        print("\n" + "=" * 80)
        print("REPLAY COMPARISON RESULTS")
        print("=" * 80)

        # Add video details from the log data
        width = log_data['args'].get('width', 'unknown')
        height = log_data['args'].get('height', 'unknown')
        codec = log_data['args'].get('codec', 'unknown')
        duration = log_data['args'].get('duration', 'unknown')
        gop_size = log_data['args'].get('gop_size', 'unknown')
        num_segments = len(clip_start_end)

        print(f"Video Resolution: {width}x{height}")
        print(f"Codec: {codec}")
        print(f"Duration: {duration} seconds")
        print(f"Number of Segments: {num_segments}")
        print(f"GOP Size: {gop_size}")
        print()

        print(f"{'Mode':<30} {'Time (s)':<15} {'Throughput (fps)':<20}")
        print("-" * 65)

        for usage, data in sorted(results.items()):
            print(f"{data['mode']:<30} {data['time']:<15.2f} {data['throughput']:<20.2f}")

        # Find fastest method
        if results:
            fastest = min(results.items(), key=lambda x: x[1]['time'])
            highest_throughput = max(results.items(), key=lambda x: x[1]['throughput'])

            print("\nResults Summary:")
            print(f"Total frames transcoded: {segment_frames:.0f}")
            print(f"Fastest method: {results[fastest[0]]['mode']} ({fastest[1]['time']:.2f}s)")
            print(f"Highest throughput: {results[highest_throughput[0]]['mode']} ({highest_throughput[1]['throughput']:.2f} fps)")

            # Log summary with additional details
            log_step("summary", "Transcoding summary",
                    results={
                        "resolution": f"{width}x{height}",
                        "codec": codec,
                        "duration": duration,
                        "num_segments": num_segments,
                        "gop_size": gop_size,
                        "total_frames": segment_frames,
                        "fastest_method": results[fastest[0]]['mode'],
                        "fastest_time": fastest[1]['time'],
                        "highest_throughput_method": results[highest_throughput[0]]['mode'],
                        "highest_throughput": highest_throughput[1]['throughput']
                    })

        print("=" * 80)

        # Compare with original results if available
        if 'results' in log_data and log_data['results']:
            print("\n" + "=" * 80)
            print("COMPARISON WITH ORIGINAL RUN")
            print("=" * 80)

            print(f"{'Mode':<30} {'Original Time':<15} {'Replay Time':<15} {'Original FPS':<15} {'Replay FPS':<15}")
            print("-" * 90)

            for usage, data in sorted(results.items()):
                if str(usage) in log_data['results']:
                    orig_data = log_data['results'][str(usage)]
                    print(f"{data['mode']:<30} {orig_data['time']:<15.2f} {data['time']:<15.2f} {orig_data['throughput']:<15.2f} {data['throughput']:<15.2f}")

            print("=" * 90)

    except Exception as e:
        print(f"Error during replay: {e}")
        raise

def split_list(n, clip_start_end):
    k, m = divmod(len(clip_start_end), n)
    result = []
    start = 0
    for i in range(n):
        end = start + k + (1 if i < m else 0)
        result.append(clip_start_end[start:end])
        start = end
    return result


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Benchmark segmented transcoding approaches")
    parser.add_argument("-g", "--gpuid", type=int, default=0, help="GPU ID")
    parser.add_argument("-W", "--width", type=int, default=1920, help="Video width. Default is 1920")
    parser.add_argument("-H", "--height", type=int, default=1080, help="Video height. Default is 1080")
    parser.add_argument("-d", "--duration", type=int, default=5400, help="Video duration in seconds. Default is 5400")
    parser.add_argument("-fps", "--fps", type=int, default=30, help="Frames per second. Default is 30")
    parser.add_argument("-p", "--preset", type=str, default="P1", help="Encoding preset (P1-P7). Default is P1")
    parser.add_argument("-ic", "--input-codec", type=str, default="h264",
                      choices=["h264", "hevc", "av1"],
                      help="Input codec to use for generating the video. Default is h264")
    parser.add_argument("-c", "--codec", type=str, default="h264",
                      choices=["h264", "hevc", "av1"],
                      help="Output codec to use for transcoding. Default is h264")
    parser.add_argument("-ibf", "--input-bframes", type=int, default=2,
                      help="Number of B-frames for input video generation. Default is 2")
    parser.add_argument("-bf", "--bframes", type=int, default=0,
                      help="Number of B-frames for output transcoding. Default is 0")
    parser.add_argument("-n", "--numthreads", type=int, default=1, help="Number of threads. Default is 1")
    parser.add_argument("-s", "--segments", type=int, default=10, help="Number of random segments. Default is 10")
    parser.add_argument("-u", "--usage", type=int, nargs='*', default=None,
                      help="Transcoding method (0: PyNVC, 1: FFmpeg without map, 2: FFmpeg stream-aware, 3: FFmpeg frame-by-frame). Default is [0, 1, 2, 3]")
    parser.add_argument("--chunk-size", type=int, default=5, help="Number of segments to process in a single FFmpeg command. Default is 5")
    parser.add_argument("--segment-duration", type=int, default=5, help="Duration of each segment in seconds. Default is 5")
    parser.add_argument("--log", type=str, help="Path to save log file")
    parser.add_argument("--random-seed", type=int, help="Random seed for reproducible segment generation")
    parser.add_argument("--gop-size", type=int, default=250, help="GOP size for encoding. Default is 250")
    parser.add_argument("-i", "--input", type=str, help="Input video file (instead of generating using ffmpeg)")
    parser.add_argument("--replay", type=str, help="Path to log file for replay")
    parser.add_argument("--ffmpeg", type=str, default="ffmpeg", help="Path to the FFmpeg executable. Default is ffmpeg")

    args = parser.parse_args()

    # Set default usages if none provided
    if args.usage is None:
        args.usage = [0, 1, 2, 3]

    return args


if __name__ == "__main__":
    script_start_time = time.perf_counter()

    args = parse_args()

    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)

    # Generate default log filename if not specified
    if not args.log and not args.replay:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        args.log = f"logs/run_{timestamp}.json"

    # Initialize log data
    log_data["timestamp"] = datetime.datetime.now().isoformat()
    log_data["args"] = vars(args)

    # Replay mode
    if args.replay:
        # Open log file in append mode to add replay results
        replay_log_path = f"logs/replay_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(replay_log_path, 'w') as log_file:
            log_data = {
                "timestamp": datetime.datetime.now().isoformat(),
                "replay_source": args.replay,
                "steps": [],
                "results": {}
            }
            json.dump(log_data, log_file, indent=2)
            replay_from_log(args.replay)
    else:
        # Normal execution mode
        # Open log file
        log_file = open(args.log, 'w')
        json.dump(log_data, log_file, indent=2)

        print(f"Logging to: {args.log}")

        # In the video generation part
        if not args.input:
            # Generate the Mandelbrot video with the specified input codec
            # Use a simple base name - generate_mandelbrot_video will add codec/resolution suffix
            base_video_path = "source_videos/mandelbrot.mp4"
            os.makedirs("source_videos", exist_ok=True)

            # Construct the expected filename (matches the naming in generate_mandelbrot_video)
            expected_video_path = f"source_videos/mandelbrot_{args.input_codec}_{args.width}x{args.height}_{args.duration}s_{args.fps}fps_gop{args.gop_size}_bf{args.input_bframes}.mp4"

            # Check if video already exists
            if os.path.exists(expected_video_path):
                print("=" * 80)
                print(f"STEP 1: USING EXISTING MANDELBROT VIDEO")
                print(f"Found existing video: {expected_video_path}")
                print("=" * 80)
                video_path = expected_video_path
                log_step("video_reuse", f"Reusing existing video: {expected_video_path}",
                        params={"width": args.width, "height": args.height, "duration": args.duration,
                               "fps": args.fps, "codec": args.input_codec, "bframes": args.input_bframes,
                               "output_path": expected_video_path, "gop_size": args.gop_size})
            else:
                print("=" * 80)
                print(f"STEP 1: GENERATING MANDELBROT VIDEO WITH {args.input_codec.upper()} CODEC")
                print(f"Using {args.input_bframes} B-frames for input video generation")
                print("=" * 80)

                input_encoder = resolve_ffmpeg_encoder(args.input_codec, current_backend())
                video_path = generate_mandelbrot_video(
                    args.width, args.height, args.duration, args.fps,
                    base_video_path, args.gop_size, args.input_codec, args.input_bframes,
                    args.ffmpeg, input_encoder
                )
        else:
            # User provided an input video
            video_path = args.input
            print("=" * 80)
            print(f"STEP 1: USING USER-PROVIDED INPUT VIDEO")
            print(f"Input video: {video_path}")
            print("=" * 80)
            log_step("video_input", f"Using user-provided input video: {video_path}",
                    params={"input_path": video_path})

        # Configure encoding parameters based on output codec
        backend = current_backend()
        config = {
            "preset": args.preset.upper(),
            "width": args.width,
            "height": args.height,
            "codec": args.codec.lower(),  # This is the output codec
            "tuning_info": "high_quality",
            "bf": str(args.bframes),  # Use the bframes parameter from args
            "gop": str(args.gop_size),
            "ffmpeg_path": args.ffmpeg,
            "backend": backend,
            "ffmpeg_encoder": resolve_ffmpeg_encoder(args.codec, backend),
        }
        log_data["args"]["config"] = config

        # Set random seed if provided for reproducible segment generation
        if args.random_seed is not None:
            random.seed(args.random_seed)
            log_step("initialization", f"Set random seed to {args.random_seed}")

        log_step("initialization", "Using PyNvVideoCodec-managed GPU context")

        # Create random segments
        print("\n" + "=" * 80)
        print("STEP 2: CREATING RANDOM SEGMENTS")
        print("=" * 80)

        clip_start_end = generate_random_segments(args.duration, args.segments, min_segment_duration=args.segment_duration)

        # Log segment creation
        segment_data = [{"start": start, "end": end} for start, end in clip_start_end]
        log_step("segment_creation", f"Created {len(clip_start_end)} random segments",
                params={"num_segments": args.segments, "min_duration": 1.0, "duration": args.duration},
                results={"segments": segment_data})

        # Print segments
        print(f"Created {len(clip_start_end)} random segments:")
        for i, (start, end) in enumerate(clip_start_end):
            print(f"  Segment {i+1}: {start:.2f}s - {end:.2f}s (duration: {end-start:.2f}s)")

        # Calculate total frames to transcode
        segment_frames = sum((end - start) * args.fps for start, end in clip_start_end)

        # Store results for comparison
        results = {}

        # Run transcoding for each usage mode
        for usage in args.usage:
            if usage not in [0, 1, 2, 3]:
                print(f"Warning: Invalid usage mode {usage}. Skipping...")
                log_step("warning", f"Invalid usage mode {usage}, skipping")
                continue

            print("\n" + "=" * 80)
            print(f"STEP 3: TRANSCODING SEGMENTS USING MODE {usage}")
            print("=" * 80)

            # Get mode description
            mode_desc = {
                0: "PyNVC transcoding",
                1: "FFmpeg without map",
                2: "FFmpeg with map (no audio)",
                3: "FFmpeg with map (with audio)"
            }.get(usage, "Unknown mode")

            print(f"Running: {mode_desc}")

            # Log transcoding start
            log_step("transcoding", f"Starting transcoding with mode {usage} ({mode_desc})",
                    params={"usage": usage, "mode": mode_desc, "numthreads": args.numthreads,
                            "chunk_size": args.chunk_size, "video_path": video_path})
            clip_chunks = split_list(args.numthreads, clip_start_end)
            threads = []
            thread_errors = []

            def thread_wrapper(chunk):
                try:
                    segmented_transcode([
                        video_path,
                        chunk,
                        config,
                        args.fps,
                        usage,
                        args.chunk_size,
                    ])
                except Exception as exc:
                    thread_errors.append(exc)

            starttime = time.time()

            for m in range(0, args.numthreads):
                t = threading.Thread(target=thread_wrapper, args=(clip_chunks[m],))
                t.start()
                #
                threads.append(t)

            for t in threads:
                t.join()

            if thread_errors:
                raise RuntimeError(f"{len(thread_errors)} transcoding thread(s) failed; first error: {thread_errors[0]}")

            endtime = time.time()
            total_time = endtime - starttime
            throughput = segment_frames / total_time if total_time > 0 else 0

            # Store results
            results[usage] = {
                'mode': mode_desc,
                'time': total_time,
                'throughput': throughput
            }

            # Log transcoding completion
            log_step("transcoding_complete", f"Completed transcoding with mode {usage}",
                    params={"usage": usage, "mode": mode_desc},
                    results={"time": total_time, "throughput": throughput})

            print(f"Completed {mode_desc}")
            print(f"Processing time: {total_time:.2f} seconds")
            print(f"Throughput: {throughput:.2f} frames/second")

        # Store results in log data
        log_data["results"] = {str(usage): {"time": data["time"], "throughput": data["throughput"]}
                            for usage, data in results.items()}

        # Print comparison results with additional details
        print("\n" + "=" * 80)
        print("COMPARISON RESULTS")
        print("=" * 80)

        # Add video details above the table
        print(f"Video Resolution: {args.width}x{args.height}")
        print(f"Codec: {args.codec}")
        print(f"Duration: {args.duration} seconds")
        print(f"Number of Segments: {len(clip_start_end)}")
        print(f"GOP Size: {args.gop_size}")
        print()

        print(f"{'Mode':<30} {'Time (s)':<15} {'Throughput (fps)':<20}")
        print("-" * 65)

        for usage, data in sorted(results.items()):
            print(f"{data['mode']:<30} {data['time']:<15.2f} {data['throughput']:<20.2f}")

        # Find fastest method
        if results:
            fastest = min(results.items(), key=lambda x: x[1]['time'])
            highest_throughput = max(results.items(), key=lambda x: x[1]['throughput'])

            print("\nResults Summary:")
            print(f"Total frames transcoded: {segment_frames:.0f}")
            print(f"Fastest method: {results[fastest[0]]['mode']} ({fastest[1]['time']:.2f}s)")
            print(f"Highest throughput: {results[highest_throughput[0]]['mode']} ({highest_throughput[1]['throughput']:.2f} fps)")

            # Log summary with additional details
            log_step("summary", "Transcoding summary",
                    results={
                        "resolution": f"{args.width}x{args.height}",
                        "codec": args.codec,
                        "duration": args.duration,
                        "num_segments": len(clip_start_end),
                        "gop_size": args.gop_size,
                        "total_frames": segment_frames,
                        "fastest_method": results[fastest[0]]['mode'],
                        "fastest_time": fastest[1]['time'],
                        "highest_throughput_method": results[highest_throughput[0]]['mode'],
                        "highest_throughput": highest_throughput[1]['throughput']
                    })

        print("=" * 80)

        # Close log file
        if log_file:
            log_file.close()
            print(f"Log saved to: {args.log}")

    # Display total execution time
    total_time = time.perf_counter() - script_start_time
    hours = int(total_time // 3600)
    minutes = int((total_time % 3600) // 60)
    seconds = total_time % 60
    print(f"\nTotal execution time: {hours:02d}:{minutes:02d}:{seconds:06.3f} ({total_time:.3f} seconds)")