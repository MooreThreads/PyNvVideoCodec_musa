# PyNvVideoCodec MUSA 验证报告

## MUSA 版本范围

MUSA 后端仅支持 MThreads Video Codec API 13.0及以上版本，并只构建和加载 `PyNvVideoCodec_130`。

## 1. 总结

本报告基于 MUSA 构建与运行结果整理。当前 MUSA 后端已具备 PyNvVideoCodec 主要 sample 与 benchmark 主路径的运行能力。

已确认状态如下：

| 项目 | 结论 |
|---|---|
| MUSA 驱动依赖 | `musa driver >= 5.3.0` |
| MUSA 构建与安装 | 通过 |
| `PyNvVideoCodec` 包导入 | 通过 |
| 统一公开 API 名称 `PyNvEncoder` / `PyNvDecoder` | 通过 |
| 非 Jupyter sample 覆盖 | 已覆盖 `samples/basic/` 与 `samples/advanced/` 下 14 个非 Jupyter sample |
| sample 参数矩阵验证 | 62 项中 60 项通过，2 项为 MUSA 当前不支持项 |
| codec / format 矩阵验证 | 14 项全部通过：decode H.264 / HEVC / VP9 / AV1，encode H.264 / HEVC / AV1；格式为 NV12 / P010 |
| decode / encode / transcode 主要 sample 路径 | 通过 |
| benchmark 主路径 | 已完成 decode perf、frame sampling、cached decoder、segmented transcode 相关验证 |

当前未发现影响主要 sample 功能路径的系统性问题。

## 2. MUSA 平台构建方法

MUSA 构建需要安装 MUSA runtime/toolkit；MUSA 后端仅支持 MTENC 13.0。仅包含 runtime 的 Docker 镜像不能编译 MUSA Filter；至少需要以下外部头文件和库：

```text
musa.h
musa_runtime.h
musa_runtime_api.h
libmusart
libmusa
mcc
```

CMake 会在配置阶段检查这些依赖。默认从 `/usr/local/musa` 查找，也可以通过 `MUSA_ROOT` 指定 SDK 安装目录：

```bash
cmake -S . -B build_musa -DCMAKE_BUILD_TYPE=Release -DUSE_MUSA=ON
cmake --build build_musa -j8
cmake --install build_musa --prefix /tmp/pynvvideocodec-stage
```

如需指定 MUSA 架构，可额外传入：

```bash
cmake -S . -B build_musa -DCMAKE_BUILD_TYPE=Release -DUSE_MUSA=ON -DCMAKE_MUSA_ARCHITECTURES=mp_xx
```

## 3. Sample 验证结果

验证统计如下：

| 项目 | 数量 |
|---|---:|
| 非 Jupyter sample 验证项 | 62 |
| 通过项 | 60 |
| MUSA 当前不支持项 | 2 |
| 已发现非 Jupyter sample | 14 |
| 已覆盖非 Jupyter sample | 14 |
| 未覆盖非 Jupyter sample | 0 |

已覆盖的非 Jupyter sample：

| 路径 | 覆盖状态 |
|---|---|
| `samples/basic/create_video_segments.py` | 已覆盖 |
| `samples/basic/encode.py` | 已覆盖 |
| `samples/basic/simple_decode_sampling.py` | 已覆盖 |
| `samples/advanced/decode.py` | 已覆盖 |
| `samples/advanced/decode_from_memory_buffer.py` | 已覆盖 |
| `samples/advanced/decode_perf.py` | 已覆盖 |
| `samples/advanced/decode_reconfigure.py` | 已覆盖 |
| `samples/advanced/decode_sei_msg.py` | 已覆盖 |
| `samples/advanced/decode_with_cuda_control.py` | 已覆盖 |
| `samples/advanced/decode_with_low_latency.py` | 已覆盖 |
| `samples/advanced/encode_perf.py` | 已覆盖 |
| `samples/advanced/encode_reconfigure.py` | 已覆盖 |
| `samples/advanced/encode_sei_msg.py` | 已覆盖 |
| `samples/advanced/simple_decode_stats.py` | 已覆盖 |

主要通过能力如下：

| 能力 | 状态 |
|---|---|
| 基础 decode | 通过 |
| low-latency decode | 通过 |
| memory-buffer decode | 通过 |
| decode reconfigure | 通过 |
| decode SEI | 通过 |
| simple decode sampling | 通过 |
| decode perf thread / process 模式 | 通过 |
| 基础 encode H.264 / HEVC / AV1 主要路径 | 通过 |
| encode reconfigure | 通过 |
| encode SEI | 通过 |
| encode perf thread / process 模式 | 通过 |
| create video segments | 通过 |

未通过项均已归类为 MUSA 当前不支持：

| 验证项 | 分类 | 说明 |
|---|---|---|
| `simple_decode_stats_default` | MUSA 当前不支持 | `DecodedFrame.ParseDecodeStats` 当前不支持 |
| `simple_decode_stats_scanned` | MUSA 当前不支持 | `DecodedFrame.ParseDecodeStats` 当前不支持 |

## 4. Codec / Format 矩阵验证

本次在 `auto-musify-PyNvVideoCodec` Docker 容器中运行了完整的声明能力矩阵。输入/输出格式范围按照当前验证要求限定为 NV12 8-bit 和 P010 10-bit。

| 类型 | Codec | NV12 | P010 |
|---|---|---:|---:|
| Decode | H.264 | 通过 | 通过 |
| Decode | HEVC | 通过 | 通过 |
| Decode | VP9 | 通过 | 通过 |
| Decode | AV1 | 通过 | 通过 |
| Encode | H.264 | 通过 | 通过 |
| Encode | HEVC | 通过 | 通过 |
| Encode | AV1 | 通过 | 通过 |

矩阵共 14 项，全部通过。H.264、HEVC 和 AV1 的输入素材由 MUSA FFmpeg encoder 生成；VP9 因容器中没有可用的 VP9 encoder，使用用户提供的 `videos.tar.gz` 中的现有 VP9 测试源进行 decode 验证。VP9 P010 用例验证了解码路径，但现有测试源的码流像素格式为 8-bit `yuv420p`，不代表独立生成的 10-bit VP9 码流。

## 5. Benchmark 验证结论

### 5.1 Decode perf

MUSA decode perf 主路径通过。

| 分辨率 | MUSA per-frame |
|---|---:|
| 360p | 1.016 ms |
| 720p | 1.213 ms |
| 1080p | 1.649 ms |


### 5.2 Encode perf

H.264 encode perf thread 模式通过。

```text
Total frames processed: 300
Total FPS: 356.09
Average FPS per thread: 356.09
```

### 5.3 Frame sampling / seek

`frame_sampling_benchmark.py` 的 PyNvVideoCodec 解码与采样主流程通过。

| 场景 | T1 FPS | T1 Eff | T2 FPS | T2 Eff |
|---|---:|---:|---:|---:|
| `250gop / 3_random_frames` | 15.4 | 2.80x | 22.2 | 1.39x |
| `250gop / 3_uniform_frames` | 19.8 | 1.09x | 43.6 | 1.09x |
| `250gop / first_30_frames` | 318.2 | N/A | 577.4 | N/A |
| `30gop / 3_random_frames` | 31.9 | 2.01x | 80.2 | 2.77x |
| `30gop / 3_uniform_frames` | 91.4 | 4.78x | 248.0 | 5.79x |
| `30gop / first_30_frames` | 305.5 | N/A | 561.4 | N/A |

### 5.4 Cached decoder

cached decoder 功能路径通过。

### 5.5 Segmented transcode

| 模式 | 结论 |
|---|---|
| Mode 0 PyNVC transcoding | 通过 |
| Mode 1 FFmpeg without map | 通过 |
| Mode 2 FFmpeg with map, no audio | 通过 |
| Mode 3 FFmpeg with map, with audio | 通过 |

## 6. 当前不支持

| 类型 | 项目 | 结论 |
|---|---|---|
| 平台能力不支持 | decode stats / `DecodedFrame.ParseDecodeStats` | 不支持 |
| 平台能力不支持 | 4:2:2 / NV16 / P216 | 不支持 |

## 7. 最终结论

当前 MUSA backend 已完成主要功能路径和声明 codec/format 矩阵验证。完整验证共 62 项，其中 60 项通过，2 项为明确的 decode stats 不支持项；另有 14 项 codec/format 矩阵全部通过。

已验证的 codec 能力为：decode H.264 / HEVC / VP9 / AV1，encode H.264 / HEVC / AV1；当前矩阵格式为 NV12 8-bit 和 P010 10-bit。

当前没有影响主要 sample 功能路径的系统性问题。
