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

from fileinput import filename
import argparse
import os
import subprocess
import time
import random
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from concurrent.futures import wait
try:
    import pycuda.driver as cuda
except ImportError:
    cuda = None
import PyNvVideoCodec as nvc
from itertools import product
from typing import List, Dict, Any, Optional
from tabulate import tabulate
import json
from datetime import datetime
from dataclasses import dataclass, asdict
import threading
import matplotlib.pyplot as plt
import numpy as np
import glob
from tqdm import tqdm

"""
Cached Decoder Benchmark

This script measures and compares the performance of NVIDIA's video decoder in two modes:
1. Simple Decoder: Creates a new decoder instance for each video
2. Cached Decoder: Reuses the same decoder instance across multiple videos

The benchmark generates test videos in different resolutions (360p, 480p, 720p, 1080p, 4K) and durations (2s and 30s),
then measures decoding performance in terms of FPS (Frames Per Second) and total frames decoded.

Features:
- Supports multiple video codecs (H.264, HEVC, AV1)
- Tests different thread counts (N NVDECs)
- Generates performance plots comparing simple vs cached decoder
- Saves results in both JSON and CSV formats
- Creates bar graphs for visual performance comparison

NOTE 1: The video clips are generated using FFmpeg only for the first run. Subsequent runs will use the generated video clips.

NOTE 2: The clips are stored in the benchmark_videos directory. The script generates 1 video clip per resolution per duration type and reuse the same clip 500 times.

NOTE 3: The script will run the decoders in multiple threads. Number of threads is determined by the --nvdecs argument.
To saturate all the NVDECs and get maximum benefit, run the script with --nvdecs <number_of_nvdecs> as a multiple of the number of NVDecs available on the system.
Use this link to check the number of NVDecs available on the system: https://developer.nvidia.com/video-encode-decode-support-matrix

NOTE 4: Since the script benchmarks decoding performance on 500 videos per resolution per duration type, it takes some time to run.

NOTE 5: If the progress bar is affecting the performance measurements, you can disable it by passing --no-progress argument.

Required Arguments:
    --nvdecs: Number of NVDECs to use

Command Line Arguments:
    --plot-only: Only generate plots from existing JSON files (default: False)
    --codec: Video codec to use (h264, hevc, or av1) (default: h264)
    --fps: Frame rate for video generation (default: 30)
    --gop: GOP size for video generation (default: 60)
    --no-progress: Disable progress bars during decoding (default: False)

Usage Examples:
    1. Run full benchmark with default settings (H.264):
       python cached_decoder_benchmark.py --nvdecs 3 (for 3 threads)

    2. Run benchmark with HEVC codec and 4 threads:
       python cached_decoder_benchmark.py --nvdecs 4 --codec hevc

    3. Generate plots from existing results:
       python cached_decoder_benchmark.py --nvdecs 3 --plot-only

    4. Run benchmark with custom video settings:
       python cached_decoder_benchmark.py --nvdecs 2 --codec av1 --fps 60 --gop 120

Output Files:
    - JSON results: cached_decoder_performance_{codec}_{threads}_threads.json
    - Performance plots: cached_decoder_performance_{codec}_{threads}_threads.png
    - Test videos: test_videos_{codec}/short_videos/ and test_videos_{codec}/long_videos/


"""

@dataclass
class DecoderResult:
    time_taken: float
    fps: float
    frames: int

@dataclass
class ResolutionResult:
    resolution: str
    new_decoder: DecoderResult
    cached_decoder: DecoderResult

    def to_dict(self):
        return asdict(self)

@dataclass
class DurationResult:
    duration_type: str
    resolution_results: List[ResolutionResult]

    def to_dict(self):
        return {
            "duration_type": self.duration_type,
            "resolution_results": [res.to_dict() for res in self.resolution_results]
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
    return getattr(nvc, "__backend__", "cuda")


def resolve_ffmpeg_encoder(codec: str, backend: str) -> str:
    try:
        return FFMPEG_ENCODERS[backend.lower()][codec.lower()]
    except KeyError as exc:
        raise ValueError(f'Unsupported ffmpeg backend/codec combination: {backend}/{codec}') from exc


def create_test_videos(
    video_configs: List[Dict[str, Any]],
    encoding: str,
    pattern: str,
    fps: int,
    pix_fmt: str,
    ffmpeg_path: str,
    base_output_dir: str,
    duration_type: str,
    resolution: str,
    target_count: int = 1,
    cq: int = 25
) -> None:
    """Create test videos with different configurations using ffmpeg with progress tracking

    Args:
        video_configs: List of video configuration dictionaries
        encoding: Video encoding to use (e.g., 'h264_nvenc')
        pattern: Test pattern to use (e.g., 'mandelbrot')
        fps: Frames per second
        pix_fmt: Pixel format (e.g., 'yuv420p')
        ffmpeg_path: Path to ffmpeg executable
        base_output_dir: Base directory for output
        duration_type: Type of duration ('short' or 'long')
        resolution: Resolution name (e.g., '360p')
        target_count: Number of videos to generate per resolution (default: 1)
        cq: Constant Quality value
    """
    # Create resolution-specific output directory
    output_dir = os.path.join(base_output_dir, resolution)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Count existing videos
    existing_videos = []
    if os.path.exists(output_dir):
        for file in os.listdir(output_dir):
            if file.lower().endswith(".mp4"):
                existing_videos.append(file)

    existing_count = len(existing_videos)
    videos_needed = target_count - existing_count

    if videos_needed <= 0:
        print(f"Already have {existing_count} video(s) for {resolution} resolution in {duration_type} duration folder")
        return

    print(f"Generating {videos_needed} video(s) for {resolution} resolution in {duration_type} duration folder")
    videos_created = 0

    # Generate videos for this resolution with progress tracking
    for config in video_configs:
        if videos_created >= videos_needed:
            break

        # Add an index to the filename if generating multiple videos
        index_suffix = f"_{videos_created + 1}" if target_count > 1 else ""
        outfile = f"{output_dir}/{pattern}_{config['resolution']}_{config['duration']}s_{fps}fps_{config['gop']}gop_{encoding}_{pix_fmt}{index_suffix}.mp4"

        # Calculate estimated frames for progress tracking
        estimated_frames = config['duration'] * fps

        ffmpeg_cmd = [
            ffmpeg_path,
            "-y",
        ]
        if not encoding.endswith('_mtenc'):
            ffmpeg_cmd.extend(["-progress", "pipe:2"])  # Output progress to stderr
        ffmpeg_cmd.extend([
            "-f",
            "lavfi",
            "-i",
            f"{pattern}=s={config['resolution']}",
            "-t",
            str(config['duration']),
            "-c:v",
            encoding,
            "-r",
            str(fps),
            "-g",
            str(config['gop']),
            "-pix_fmt",
            pix_fmt,
        ])
        if encoding.endswith('_mtenc'):
            ffmpeg_cmd.extend(["-rc", "vbr"])
        else:
            ffmpeg_cmd.extend(["-cq", str(cq)])
        ffmpeg_cmd.append(outfile)

        try:
            # Start FFmpeg process with progress tracking
            process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     universal_newlines=True, bufsize=1)

            # Progress bar setup - single line that updates in place
            video_name = f"{pattern}_{config['resolution']}_{config['duration']}s_{fps}fps_{config['gop']}gop_{encoding}_{pix_fmt}{index_suffix}.mp4"
            pbar = tqdm(total=estimated_frames, unit='frames',
                       desc=f"Creating {video_name}",
                       ncols=80, leave=True, position=0)

            # Read stderr line by line to get progress
            current_frame = 0
            max_frame_seen = 0
            last_update_time = time.time()
            update_interval = 0.5  # Update progress bar every 0.5 seconds maximum

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

                        # Only update progress bar if enough time has passed or significant progress made
                        current_time = time.time()
                        if (current_time - last_update_time >= update_interval or
                            frame_num - current_frame >= 10):

                            # If we see more frames than expected, adjust the total
                            if frame_num > estimated_frames:
                                pbar.total = frame_num + 50  # Add buffer for final frames

                            if frame_num > current_frame:
                                # Update progress bar
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

            # If we still haven't reached the total, complete it
            if current_frame < pbar.total:
                pbar.update(pbar.total - current_frame)

            pbar.close()

            if process.returncode != 0:
                # Read any remaining stderr
                remaining_stderr = process.stderr.read()
                print(f"Error creating video: {remaining_stderr}")
                raise subprocess.CalledProcessError(process.returncode, ffmpeg_cmd, remaining_stderr)

            print(f"✓ Video creation complete: {os.path.basename(outfile)}")
            print(f"  Frames encoded: {max_frame_seen}")
            videos_created += 1

        except subprocess.CalledProcessError as e:
            print(f"FFmpeg error: {e}")
            continue
        except Exception as e:
            print(f"Error: {e}")
            continue

    print(f"Created {videos_created} new video(s) for {resolution} resolution in {duration_type} duration folder")

def split_list(videos, n):
    k, m = divmod(len(videos), n)
    result = []
    start = 0
    for i in range(n):
        end = start + k + (1 if i < m else 0)
        result.append(videos[start:end])
        start = end
    return result

def create_cuda_decode_context():
    if current_backend() == "musa":
        return None, None
    if cuda is None:
        raise RuntimeError("CUDA benchmark context setup requires pycuda to be installed")
    cuda.init()
    cuda_device = cuda.Device(0)
    cuda_ctx = cuda_device.retain_primary_context()
    cuda_ctx.push()
    return cuda_ctx, cuda.Stream()


def decoder_kwargs(cuda_ctx, cuda_stream, **kwargs):
    if cuda_ctx is not None and cuda_stream is not None:
        kwargs.update(cuda_context=cuda_ctx.handle, cuda_stream=cuda_stream.handle)
    return kwargs


def decode_using_new_decoder(clips, progress_callback=None):
    cuda_ctx, cuda_stream = create_cuda_decode_context()
    total_frames = 0

    try:
        for video_file_path in clips:
            decoder = nvc.SimpleDecoder(
                video_file_path,
                **decoder_kwargs(cuda_ctx, cuda_stream, bWaitForSessionWarmUp=True),
            )
            metadata = decoder.get_stream_metadata()
            num_frames = metadata.num_frames
            for i in range(num_frames):
                frame = decoder[i]

            total_frames += num_frames
            if progress_callback:
                progress_callback(1)
        if cuda_stream is not None:
            cuda_stream.synchronize()
    finally:
        if cuda_ctx is not None:
            cuda_ctx.pop()

    return total_frames


def decode_using_cached_decoder(clips, progress_callback=None):
    decoder = None
    cuda_ctx, cuda_stream = create_cuda_decode_context()
    total_frames = 0

    try:
        for video_file_path in clips:
            if decoder is None:
                decoder = nvc.SimpleDecoder(
                    video_file_path,
                    **decoder_kwargs(
                        cuda_ctx,
                        cuda_stream,
                        bWaitForSessionWarmUp=True,
                        max_width=3840,
                        max_height=2160,
                    ),
                )
            else:
                decoder.reconfigure_decoder(video_file_path)

            metadata = decoder.get_stream_metadata()
            num_frames = metadata.num_frames
            for i in range(num_frames):
                frame = decoder[i]

            total_frames += num_frames
            if cuda_stream is not None:
                cuda_stream.synchronize()
            if progress_callback:
                progress_callback(1)
    finally:
        if cuda_ctx is not None:
            cuda_ctx.pop()

    return total_frames

def run_thread(func, clips_chunks, N, desc="Decoding", show_progress=True):
    threads = []
    start_time = time.perf_counter()
    total_frames = 0

    # Use a list to store results from threads
    results = [0] * N

    # Calculate total videos across all chunks
    total_videos = sum(len(chunk) for chunk in clips_chunks)

    # Create a thread-safe progress bar (disabled if show_progress is False)
    pbar = tqdm(total=total_videos, unit='videos', desc=desc, ncols=100, leave=True, disable=not show_progress)
    pbar_lock = threading.Lock()

    def progress_callback(n):
        with pbar_lock:
            pbar.update(n)

    def thread_wrapper(func, clips, index, progress_cb):
        results[index] = func(clips, progress_callback=progress_cb)

    for m in range(0, N):
        t = threading.Thread(target=thread_wrapper, args=(func, clips_chunks[m], m, progress_callback))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    pbar.close()

    total_frames = sum(results)
    elapsed_time = time.perf_counter() - start_time
    return elapsed_time, total_frames

def decode_perf_results(clips_by_resolution: Dict[str, List[str]], N: int, duration_type: str, show_progress: bool = True) -> DurationResult:
    resolution_results = []

    duration_label = "2s" if duration_type == "short" else "30s"

    for resolution, clips in clips_by_resolution.items():
        clips_chunks = split_list(clips, N)

        elapsed_time_case_2, frames_case_2 = run_thread(decode_using_cached_decoder,
                             clips_chunks, N,
                             desc=f"Cached Decoder [{resolution}, {duration_label}]",
                             show_progress=show_progress)

        elapsed_time_case_1, frames_case_1 = run_thread(decode_using_new_decoder,
                             clips_chunks, N,
                             desc=f"Simple Decoder [{resolution}, {duration_label}]",
                             show_progress=show_progress)


        fps_case_1 = round(frames_case_1 / elapsed_time_case_1)
        fps_case_2 = round(frames_case_2 / elapsed_time_case_2)

        res_result = ResolutionResult(
            resolution=resolution,
            new_decoder=DecoderResult(
                time_taken=round(elapsed_time_case_1, 2),
                fps=fps_case_1,
                frames=frames_case_1
            ),
            cached_decoder=DecoderResult(
                time_taken=round(elapsed_time_case_2, 2),
                fps=fps_case_2,
                frames=frames_case_2
            )
        )
        resolution_results.append(res_result)

    return DurationResult(duration_type=duration_type, resolution_results=resolution_results)

def display_results_table(all_results: List[DurationResult]):
    headers = ["Duration Type", "Resolution", "Decoder Type", "Time Taken (s)", "FPS"]
    table_data = []

    duration_labels = {
        "short": "Short (2 sec)",
        "long": "Long (30 sec)"
    }

    for result in all_results:
        duration_label = duration_labels.get(result.duration_type, result.duration_type)

        # Add duration type header row
        table_data.append([f"{duration_label} Videos"] + ["" for _ in range(len(headers)-1)])

        print(f"\n{result.duration_type.capitalize()} duration frames decoded: {result.resolution_results[0].new_decoder.frames}\n")

        # Sort resolution results by resolution (360p, 480p, etc.)
        def resolution_key(res):
            if res.resolution == '4k':
                return 4000  # 4k is equivalent to 4000p
            return int(res.resolution.replace("p", ""))

        sorted_results = sorted(result.resolution_results, key=resolution_key)

        for res_result in sorted_results:
            # Add row for simple decoder
            table_data.append([
                "",  # Empty duration type (already shown in header)
                res_result.resolution,
                "Simple",
                res_result.new_decoder.time_taken,
                int(res_result.new_decoder.fps),  # Convert to integer
            ])
            # Add row for cached decoder
            table_data.append([
                "",  # Empty duration type (already shown in header)
                res_result.resolution,
                "Cached",
                res_result.cached_decoder.time_taken,
                int(res_result.cached_decoder.fps),  # Convert to integer
            ])

        # Add separator between duration types using the same style as header
        if result.duration_type == "short":
            table_data.append(["-" * 20, "-" * 12, "-" * 13, "-" * 16, "-" * 5, "-" * 15])

    print("\nDecoder Performance Results:")
    print(tabulate(table_data, headers=headers, tablefmt="simple", floatfmt=".2f"))

def collect_videos(base_dir, resolutions):
    videos_by_resolution = {}
    for res_name, _ in resolutions:
        res_dir = os.path.join(base_dir, res_name)
        if os.path.exists(res_dir):
            videos = []
            for file in os.listdir(res_dir):
                if file.lower().endswith(".mp4"):
                    full_path = os.path.join(res_dir, file)
                    # Add the same video 500 times to the list
                    videos.extend([full_path] * 500)
            if videos:
                videos_by_resolution[res_name] = videos
    return videos_by_resolution

def plot_decoder_performance():
    """Create bar plots for decoder performance across resolutions for each thread count"""
    # Read JSON files for the specific codec
    results = {}
    for filename in glob.glob(f"cached_decoder_performance_{args.codec}_*_threads.json"):
        # Extract thread count from filename
        thread_count = int(filename.split('_')[4])
        with open(filename, 'r') as f:
            results[thread_count] = json.load(f)

    if not results:
        print(f"No JSON files found for codec {args.codec}")
        return

    # Sort thread counts to ensure correct order
    thread_counts = sorted(results.keys())

    # Define resolution order for consistent plotting
    resolution_order = ['360p', '480p', '720p', '1080p', '4k']

    for thread_count in thread_counts:
        # Create a figure for each thread count
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

        # Extract data for this thread count
        data = {
            'short': {'new': [], 'cached': [], 'resolutions': []},
            'long': {'new': [], 'cached': [], 'resolutions': []}
        }

        # Process each duration type
        for duration_result in results[thread_count]:
            duration_type = duration_result['duration_type']

            # Sort results by resolution order
            sorted_results = sorted(
                duration_result['resolution_results'],
                key=lambda x: resolution_order.index(x['resolution'])
            )

            for res_result in sorted_results:
                data[duration_type]['resolutions'].append(res_result['resolution'])
                data[duration_type]['new'].append(res_result['new_decoder']['fps'])
                data[duration_type]['cached'].append(res_result['cached_decoder']['fps'])

        # Plot for short duration videos
        x = np.arange(len(data['short']['resolutions']))
        width = 0.35

        ax1.bar(x - width/2, data['short']['new'], width, label='Simple Decoder')
        ax1.bar(x + width/2, data['short']['cached'], width, label='Cached Decoder')
        ax1.set_title(f'Short Duration Videos (2s) - {thread_count} Thread(s) - {args.codec.upper()}')
        ax1.set_xlabel('Resolution')
        ax1.set_ylabel('FPS')
        ax1.set_xticks(x)
        ax1.set_xticklabels(data['short']['resolutions'])
        ax1.grid(True, axis='y')
        ax1.legend()

        # Plot for long duration videos
        x = np.arange(len(data['long']['resolutions']))
        ax2.bar(x - width/2, data['long']['new'], width, label='Simple Decoder')
        ax2.bar(x + width/2, data['long']['cached'], width, label='Cached Decoder')
        ax2.set_title(f'Long Duration Videos (30s) - {thread_count} Thread(s) - {args.codec.upper()}')
        ax2.set_xlabel('Resolution')
        ax2.set_ylabel('FPS')
        ax2.set_xticks(x)
        ax2.set_xticklabels(data['long']['resolutions'])
        ax2.grid(True, axis='y')
        ax2.legend()

        # Adjust layout and save
        plt.tight_layout()
        plt.savefig(f'cached_decoder_performance_{args.codec}_{thread_count}_threads.png')
        plt.close()

        print(f"Plot saved as 'cached_decoder_performance_{args.codec}_{thread_count}_threads.png'")

if __name__=="__main__":
    script_start_time = time.perf_counter()

    parser = argparse.ArgumentParser(
        'This sample application measures decoding performance in FPS.'
    )
    parser.add_argument(
        "--plot-only", action="store_true", default=False,
        help="only generate plots from existing JSON files (default: False)")
    parser.add_argument(
        "--codec", type=str, choices=['h264', 'hevc', 'av1'], default='h264',
        help="video codec to use (h264, hevc, or av1). Default: h264")
    parser.add_argument(
        "--nvdecs", type=int, required=True, help="number of NVDECs to use")
    parser.add_argument(
        "--fps", type=int, default=30, help="frame rate for video generation (default: 30)")
    parser.add_argument(
        "--gop", type=int, default=60, help="GOP size for video generation (default: 60)")
    parser.add_argument(
        "--no-progress", action="store_true", default=False,
        help="disable progress bars during decoding (default: False)")
    parser.add_argument(
        "--ffmpeg", type=str, default="ffmpeg",
        help="path to the FFmpeg executable (default: ffmpeg)")

    args = parser.parse_args()

    if args.plot_only:
        plot_decoder_performance()
        exit(0)

    # Define thread counts to test - only 1 and max threads
    num_of_threads = [args.nvdecs] if args.nvdecs > 1 else [1]

    # Define resolutions with their dimensions
    resolutions = [
        ("360p", "640x360"),
        ("480p", "854x480"),
        ("720p", "1280x720"),
        ("1080p", "1920x1080"),
        ("4k", "3840x2160")
    ]

    # Use the test videos directory in the same directory as the script
    base_videos_dir = os.path.join(os.path.dirname(__file__), f"test_videos_{args.codec}")
    short_videos_dir = os.path.join(base_videos_dir, "short_videos")
    long_videos_dir = os.path.join(base_videos_dir, "long_videos")

    # Create base directories if they don't exist
    os.makedirs(short_videos_dir, exist_ok=True)
    os.makedirs(long_videos_dir, exist_ok=True)

    # Define video generation parameters
    encoding = resolve_ffmpeg_encoder(args.codec, current_backend())
    print(f"Using FFmpeg binary: {args.ffmpeg}")
    pattern = "mandelbrot"  # Test pattern
    fps = args.fps  # Frame rate from command line
    pix_fmt = "nv12" if current_backend() == "musa" else "yuv420p"  # Standard pixel format
    gop_size = args.gop  # GOP size from command line
    cq = 25  # Constant Quality value


    ffmpeg_path = args.ffmpeg

    # Generate videos for each resolution
    for res_name, res_dim in resolutions:
        # Short duration videos
        short_video_configs = [{
            "resolution": res_dim,
            "gop": gop_size,
            "duration": 2  # Fixed 2 seconds
        }]
        create_test_videos(
            short_video_configs,
            encoding,
            pattern,
            fps,
            pix_fmt,
            ffmpeg_path,
            str(short_videos_dir),
            "short",
            res_name,
            1,  # Always generate 1 video per resolution
            cq
        )

        # Long duration videos
        long_video_configs = [{
            "resolution": res_dim,
            "gop": gop_size,
            "duration": 30  # Fixed 30 seconds
        }]
        create_test_videos(
            long_video_configs,
            encoding,
            pattern,
            fps,
            pix_fmt,
            ffmpeg_path,
            str(long_videos_dir),
            "long",
            res_name,
            1,  # Always generate 1 video per resolution
            cq
        )

    # Collect videos from all resolution directories
    short_clips = collect_videos(short_videos_dir, resolutions)
    long_clips = collect_videos(long_videos_dir, resolutions)

    all_results = []

    # Run benchmark for each thread count
    for thread_count in num_of_threads:
        print(f"\nRunning benchmark with {thread_count} thread(s)")

        if short_clips:
            print(f"\nProcessing short duration videos:")
            for res, clips in short_clips.items():
                print(f"  Generating stats for {res} short videos")
                print(f"  {res}: {len(clips)} video(s)")
            short_results = decode_perf_results(short_clips, thread_count, "short", show_progress=not args.no_progress)
            all_results.append(short_results)

        if long_clips:
            print(f"\nProcessing long duration videos:")
            for res, clips in long_clips.items():
                print(f"  Generating stats for {res} long videos")
                print(f"  {res}: {len(clips)} video(s)")
            long_results = decode_perf_results(long_clips, thread_count, "long", show_progress=not args.no_progress)
            all_results.append(long_results)

        # Print video configuration details
        print("\nVideo Configuration:")
        print(f"Pattern: {pattern}")
        print(f"Frame Rate: {fps} fps")
        print(f"GOP Size: {gop_size}")
        print(f"Number of threads: {thread_count}")


        if all_results:
            # Display tabulated results
            display_results_table(all_results)

            # Save results to JSON file with codec and thread count in filename
            filename = f"cached_decoder_performance_{args.codec}_{thread_count}_threads.json"

            # Convert dataclass objects to dictionaries
            results_dict = [result.to_dict() for result in all_results]

            with open(filename, 'w') as f:
                json.dump(results_dict, f, indent=4)

            print(f"\nResults saved to {filename}")

            # Clear results for next thread count
            all_results = []
        else:
            print("No videos were found or generated. Please check the directory structure and video generation process.")

    # After running the benchmark, generate plots
    plot_decoder_performance()

    # Display total execution time
    total_time = time.perf_counter() - script_start_time
    hours = int(total_time // 3600)
    minutes = int((total_time % 3600) // 60)
    seconds = total_time % 60
    print(f"\nTotal execution time: {hours:02d}:{minutes:02d}:{seconds:06.3f} ({total_time:.3f} seconds)")