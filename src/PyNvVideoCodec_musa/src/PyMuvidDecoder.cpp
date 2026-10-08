/*
 * This copyright notice applies to this file only
 *
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: MIT
 *
 * Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software and associated documentation files (the "Software"),
 * to deal in the Software without restriction, including without limitation
 * the rights to use, copy, modify, merge, publish, distribute, sublicense,
 * and/or sell copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
 * DEALINGS IN THE SOFTWARE.
 */

#include "ExternalBuffer.hpp"
#include "PyMuvidDecoder.hpp"
#include "PyNvVideoCodecUtils.hpp"

#include <functional>

using namespace std;
using time_point_ms
= std::chrono::time_point<std::chrono::system_clock, std::chrono::milliseconds>;

namespace py = pybind11;

PyMuvidDecoder::PyMuvidDecoder(
    int _gpuid,
    musaVideoCodec _codec,
    size_t _context,
    size_t _stream,
    bool m_bUseDeviceFrame,
    bool _enableasyncallocations,
    int maxWidth,
    int maxHeight,
    OutputColorType outputColorType,
    bool _enableSEIMessage,
    bool bWaitForSessionWarmUp,
    DisplayDecodeLatency latency,
    bool enableDecodeStats
) : mReleasePrimaryContext(false),
    mGPUId(_gpuid)
{
    try {
        ck(muInit(0));
        ValidateGpuId(mGPUId);
        if (_context)
        {
            ValidateMUSAContext(_gpuid, reinterpret_cast<MUcontext>( _context));
            cuContext = reinterpret_cast<MUcontext>( _context);
        }
        else
        {
            ck(muDevicePrimaryCtxRetain(&cuContext, mGPUId));
            mReleasePrimaryContext = true;
        }

        if(_stream)
        {
            ValidateMUSAStream(reinterpret_cast<MUstream>(_stream), cuContext);
            cuStream = reinterpret_cast<MUstream>(_stream);
        }
        bool bLowLatency = false;
        bool bZeroLatency = false;
        
        switch (latency)
        {
        case DisplayDecodeLatency::DISPLAYDECODELATENCY_NATIVE:
            bLowLatency = false;
            bZeroLatency = false;
            break;
        case DisplayDecodeLatency::DISPLAYDECODELATENCY_LOW:
            bLowLatency = true;
            bZeroLatency = false;
            break;
        case DisplayDecodeLatency::DISPLAYDECODELATENCY_ZERO:
            bLowLatency = true;
            bZeroLatency = true;
            break;
        default:
            break;
        }
        decoder.reset(new MuvidDecoder(_gpuid, cuStream, cuContext, m_bUseDeviceFrame, _codec, bLowLatency,
            _enableasyncallocations, maxWidth, maxHeight, outputColorType,false, _enableSEIMessage,1000U, bZeroLatency,bWaitForSessionWarmUp, enableDecodeStats));
    }
    catch (const PyNvVCException<PyNvVCGenericError>& e) {
        // Re-throw PyNvVCException as-is
        throw;
    }
    catch (const PyNvVCException<PyNvVCUnsupported>& e) {
        // Re-throw PyNvVCException as-is
        throw;
    }
    catch (const std::exception& e) {
        // Convert standard exceptions to PyNvVCException
        PYNVVC_THROW_ERROR(std::string("PyMuvidDecoder constructor failed: ") + e.what(), MUSA_ERROR_UNKNOWN);
    }
    catch (...) {
        // Convert unknown exceptions to PyNvVCException
        PYNVVC_THROW_ERROR("PyMuvidDecoder constructor failed with unknown error", MUSA_ERROR_UNKNOWN);
    }
}

PyMuvidDecoder::~PyMuvidDecoder()
{
    decoder.reset();
    if (mReleasePrimaryContext)
    {
        ck(muDevicePrimaryCtxRelease(mGPUId));
    }
}

uint8_t* PyMuvidDecoder::GetLockedFrame(int64_t* pTimestamp)
{
    NVTX_SCOPED_RANGE("py::GetLockedFrame")
    SEI_MESSAGE seimsg = {};
    MUevent event = nullptr;
    uint8_t *pDecodeStats = nullptr;
    uint8_t* framePtr = (decoder->GetLockedFrame(pTimestamp, &seimsg, &event, &pDecodeStats));
    
    return framePtr;
}

void PyMuvidDecoder::UnlockFrame(uint8_t* framePtr)
{
    NVTX_SCOPED_RANGE("py::UnlockFrame")
    decoder->UnlockFrame(framePtr);
}

int PyMuvidDecoder::GetNumDecodedFrame(const PacketData packetData)
{
    NVTX_SCOPED_RANGE("py::GetNumDecodedFrame")
    py::gil_scoped_release release;
    int nFlags = packetData.bDiscontinuity? MUVID_PKT_DISCONTINUITY : 0;
    int  numFrames = decoder->Decode((uint8_t*)packetData.bsl_data, packetData.bsl, nFlags, packetData.pts);
    py::gil_scoped_acquire acquire;
    return numFrames;
}


std::vector<DecodedFrame> PyMuvidDecoder::Decode(const PacketData packetData)
{
    NVTX_SCOPED_RANGE("py::decode")
    std::vector<DecodedFrame> frames;
    py::gil_scoped_release release;
    auto vecTupFrame = decoder->PyDecode((uint8_t*)packetData.bsl_data, packetData.bsl, packetData.pts, packetData.decode_flag);
    auto funcCAIDLPack = std::bind(GetCAIMemoryViewAndDLPack, decoder.get(), std::placeholders::_1);
    std::transform(vecTupFrame.begin(), vecTupFrame.end(), std::back_inserter(frames), funcCAIDLPack);
    py::gil_scoped_acquire acquire;
    return frames;
}


DecodedFrame PyMuvidDecoder::GetFrame()
{
    NVTX_SCOPED_RANGE("py::GetFrame")

    int64_t timestamp;
    SEI_MESSAGE seimsg;
    MUevent event = nullptr;
    uint8_t *pDecodeStats;
    
    MUdeviceptr  data = (MUdeviceptr)decoder->GetFrame(&timestamp, &seimsg, &event, &pDecodeStats);
    
    DecodedFrame frame = GetCAIMemoryViewAndDLPack(decoder.get(), std::make_tuple(data, timestamp, seimsg, event, pDecodeStats));
    
    return frame;
}

using CAPS = std::unordered_map<std::string, uint32_t>;

static CAPS PyMuvidDecoderCaps(
            int32_t gpuid,
            musaVideoCodec codec,
            musaVideoChromaFormat chromaformat,
            uint32_t bitdepth
            )
{
    CuvidFunctions api{};
    const char* err = loadCuvidSymbols(&api,
#ifdef _WIN32
        "mtmuvid.dll");
#else
        "libvideo_musa.so");
#endif
    if (err) {
        constexpr const char* explanation =
#if defined(_WIN32)
            "Could not dynamically load mtmuvid.dll. Please ensure "
            "Nvidia Graphics drivers are correctly installed!";
#else
            "Could not dynamically load libvideo_musa.so. Please "
            "ensure Nvidia Graphics drivers are correctly installed!\n"
            "If using Docker please make sure that your Docker image was "
            "launched with \"video\" driver capabilty (see "
            "https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/"
            "user-guide.html#driver-capabilities)";
#endif
        auto description = muvid_dlerror();
        if (description) {
            throw std::runtime_error(std::string(err) + ": " +
                std::string(description) + "\n" + explanation);
        }
        else {
            throw std::runtime_error(std::string(err) + "\n" + explanation);
        }
    }
    
    muInit(0);
    ValidateGpuId(gpuid);
    int32_t iGPU = 0;
    MUdevice muDevice = 0;
    MUcontext musacontext;
    muDeviceGet(&muDevice, iGPU);
    PYNVC_MUSA_CTX_CREATE(&musacontext, 0, muDevice);
    MUVIDDECODECAPS decodecaps;
    memset(&decodecaps, 0, sizeof(decodecaps));
    decodecaps.eCodecType      = codec;
    decodecaps.eChromaFormat   = chromaformat;
    decodecaps.nBitDepthMinus8 = bitdepth - 8;
    MUSA_DRVAPI_CALL(muCtxPushCurrent(musacontext));
    MUVID_API_CALL(api.muvidGetDecoderCaps(&decodecaps));
    MUSA_DRVAPI_CALL(muCtxPopCurrent(NULL));
    muCtxDestroy(musacontext);
    unloadCuvidSymbols(&api);

    CAPS caps;
    caps["codec_id"]            = decodecaps.eCodecType;
    caps["chromaformat_id"]     = decodecaps.eChromaFormat;
    caps["bitdepth"]            = decodecaps.nBitDepthMinus8 + 8;
    caps["supported"]           = decodecaps.bIsSupported;
    caps["num_decoder_engines"] = decodecaps.nNumMTDECs;
    caps["width_max"]           = decodecaps.nMaxWidth;
    caps["height_max"]          = decodecaps.nMaxHeight;
    caps["mb_num_max"]          = decodecaps.nMaxMBCount;
    caps["width_min"]           = decodecaps.nMinWidth;
    caps["height_min"]          = decodecaps.nMinHeight;

    return caps;
}

void Init_PyMuvidDecoder(py::module& m)
{
    py::enum_<musaVideoCodec>(m, "cudaVideoCodec", py::module_local())
        .ENUM_VALUE(musaVideoCodec, MPEG1)
        .ENUM_VALUE(musaVideoCodec, MPEG2)    /**<  MPEG2             */
        .ENUM_VALUE(musaVideoCodec, MPEG4)    /**<  MPEG4             */
        .ENUM_VALUE(musaVideoCodec, VC1)      /**<  VC1               */
        .ENUM_VALUE(musaVideoCodec, H264)     /**<  H264              */
        .ENUM_VALUE(musaVideoCodec, JPEG)     /**<  JPEG              */
        .ENUM_VALUE(musaVideoCodec, H264_SVC) /**<  H264-SVC          */
        .ENUM_VALUE(musaVideoCodec, H264_MVC) /**<  H264-MVC          */
        .ENUM_VALUE(musaVideoCodec, HEVC)     /**<  HEVC              */
        .ENUM_VALUE(musaVideoCodec, VP8)      /**<  VP8               */
        .ENUM_VALUE(musaVideoCodec, VP9)      /**<  VP9               */
        .ENUM_VALUE(musaVideoCodec, AV1)      /**<  AV1               */
        //.ENUM_VALUE(musaVideoCodec_, NumCodecs) /**<  Max codecs        */
        // Uncompressed YUV     --------------> we should remove these YUV formats??
        .ENUM_VALUE(musaVideoCodec, YUV420)
        .ENUM_VALUE(musaVideoCodec, YV12)
        .ENUM_VALUE(musaVideoCodec, NV12)
        .ENUM_VALUE(musaVideoCodec, YUYV)
        .ENUM_VALUE(musaVideoCodec, UYVY);

    py::enum_<musaVideoSurfaceFormat>(m, "cudaVideoSurfaceFormat", py::module_local())
        .ENUM_VALUE(musaVideoSurfaceFormat, NV12)
        .ENUM_VALUE(musaVideoSurfaceFormat, P016)
        .ENUM_VALUE(musaVideoSurfaceFormat, YUV444)
        .ENUM_VALUE(musaVideoSurfaceFormat, YUV444_16Bit)
        .ENUM_VALUE(musaVideoSurfaceFormat, NV16)
        .ENUM_VALUE(musaVideoSurfaceFormat, P216);

    py::enum_<Pixel_Format>(m, "Pixel_Format", py::module_local())
        .ENUM_VALUE(Pixel_Format, NV12)
        .ENUM_VALUE(Pixel_Format, YUV444)
        .ENUM_VALUE(Pixel_Format, P016)
        .ENUM_VALUE(Pixel_Format, YUV444_16Bit)
        .ENUM_VALUE(Pixel_Format, NV16)
        .ENUM_VALUE(Pixel_Format, P216)
        .ENUM_VALUE(Pixel_Format, RGB)
        .ENUM_VALUE(Pixel_Format, RGBP);

    py::enum_<musaVideoChromaFormat>(m, "cudaVideoChromaFormat", py::module_local())
        .ENUM_VALUE(musaVideoChromaFormat, Monochrome)
        .ENUM_VALUE(musaVideoChromaFormat, 420)
        .ENUM_VALUE(musaVideoChromaFormat, 422)
        .ENUM_VALUE(musaVideoChromaFormat, 444);

    py::enum_<SEI_H264_HEVC_MPEG2_PAYLOAD_TYPE>(m, "SEI_TYPE")
        .ENUM_VALUE(SEI_TYPE, TIME_CODE_H264)
        .ENUM_VALUE(SEI_TYPE, USER_DATA_REGISTERED)
        .ENUM_VALUE(SEI_TYPE, USER_DATA_UNREGISTERED)
        .ENUM_VALUE(SEI_TYPE, TIME_CODE)
        .ENUM_VALUE(SEI_TYPE, MASTERING_DISPLAY_COLOR_VOLUME)
        .ENUM_VALUE(SEI_TYPE, CONTENT_LIGHT_LEVEL_INFO)
        .ENUM_VALUE(SEI_TYPE, ALTERNATIVE_TRANSFER_CHARACTERISTICS);

    py::class_<PyMuvidDecoder, shared_ptr<PyMuvidDecoder>> pyNvDecoder(m, "PyNvDecoder", py::module_local());

    m.def(
        "CreateDecoder",
        [](
            int gpuid,
            musaVideoCodec codec,
            size_t musacontext,
            size_t musastream,
            bool usedevicememory,
            int maxwidth,
            int maxheight,
            OutputColorType outputColorType,
            bool enableSEIMessage,
            bool bWaitForSessionWarmUp,
            DisplayDecodeLatency latency,
            bool enableDecodeStats
            )
        {
            return std::make_shared<PyMuvidDecoder>(gpuid, codec, musacontext, musastream, usedevicememory, false, maxwidth, maxheight,outputColorType,enableSEIMessage, bWaitForSessionWarmUp, latency, enableDecodeStats);
        },

        py::arg("gpuid") = 0,
            py::arg("codec") = musaVideoCodec::musaVideoCodec_H264,
            py::arg("cudacontext") = 0,
            py::arg("cudastream") = 0,
            py::arg("usedevicememory") = 0,
            py::arg("maxwidth") = 0,
            py::arg("maxheight") = 0,
            py::arg("outputColorType") = OutputColorType::NATIVE,
            py::arg("enableSEIMessage") = 0,
            py::arg("bWaitForSessionWarmUp") = 0,
            py::arg("latency") = DisplayDecodeLatency::DISPLAYDECODELATENCY_NATIVE,
            py::arg("enableDecodeStats") = 0,
            R"pbdoc(
        Initialize decoder with set of particular
        parameters
        :param gpuid: GPU Id
        :param codec : Video Codec
        :param cudacontext : MUSA context (kept as CUDA-compatible keyword name)
        :param cudastream : MUSA stream (kept as CUDA-compatible keyword name)
        :param use_device_memory : decoder output surface is in device memory if true else on host memory
        :param maxwidth : maximum width set by application for the decoded surface
        :param maxheight : maximum height set by application for the decoded surface
        :param outputColorType : Output format type of the decoded frames
        :param enableSEIMessage : enable SEI message extraction
        :param bWaitForSessionWarmUp : Wait for all threads to finish initialization of the decoder session.
        :param latency : "DISPLAYDECODELATENCY_NATIVE - Decoder input and output have a latency of 4 frames, output in display order"
                         "DISPLAYDECODELATENCY_LOW - Decoder input and output have a latency of 0 frames, output in display order"
                         "DISPLAYDECODELATENCY_ZERO - Decoder input and output have a latency of 0 frames, output in decode order"
        :param enableDecodeStats : enable decode statistics collection
    )pbdoc"
            )
        .def(
            "CreateDecoder",
            [](
                int gpuid,
                musaVideoCodec codec,
                size_t musacontext,
                size_t musastream,
                bool usedevicememory,
                bool enableasyncallocations,
                int maxwidth,
                int maxheight,
                OutputColorType outputColorType,
                bool enableSEIMessage,
                DisplayDecodeLatency latency,
                bool enableDecodeStats
                )
            {
                return std::make_shared<PyMuvidDecoder>(gpuid, codec, musacontext, musastream, true, enableasyncallocations, maxwidth, maxheight, outputColorType ,enableSEIMessage,true, latency, enableDecodeStats);
            },

            py::arg("gpuid") = 0,
                py::arg("codec") = musaVideoCodec::musaVideoCodec_H264,
                py::arg("cudacontext") = 0,
                py::arg("cudastream") = 0,
                py::arg("usedevicememory") = 1,
                py::arg("enableasyncallocations") = 1,
                py::arg("maxwidth") = 0,
                py::arg("maxheight") = 0,
                py::arg("outputColorType") = OutputColorType::NATIVE,
                py::arg("enableSEIMessage") = 0,
                py::arg("latency") = DisplayDecodeLatency::DISPLAYDECODELATENCY_NATIVE,
                py::arg("enableDecodeStats") = 0,
                R"pbdoc(
        Initialize decoder with set of particular
        parameters
        :param gpuid: GPU Id
        :param codec : Video Codec
        :param cudacontext : MUSA context (kept as CUDA-compatible keyword name)
        :param cudastream : MUSA stream (kept as CUDA-compatible keyword name)
        :param use_device_memory : decoder output surface is in device memory if true else on host memory
        :param maxwidth : maximum width set by application for the decoded surface
        :param maxheight : maximum height set by application for the decoded surface
        :param outputColorType : Output format type of the decoded frames
        :param enableSEIMessage : enable SEI message extraction
        :param latency : "DISPLAYDECODELATENCY_NATIVE - Decoder input and output have a latency of 4 frames, output in display order"
                         "DISPLAYDECODELATENCY_LOW - Decoder input and output have a latency of 0 frames, output in display order"
                         "DISPLAYDECODELATENCY_ZERO - Decoder input and output have a latency of 0 frames, output in decode order"
        :param enableDecodeStats : enable decode statistics collection
    )pbdoc"
    );

    m.def(
        "GetDecoderCaps",
        [](
            int32_t gpuid,
            musaVideoCodec codec,
            musaVideoChromaFormat chromaformat,
            uint32_t bitdepth
            )
        {
            return PyMuvidDecoderCaps(gpuid, codec, chromaformat, bitdepth);
        },

        py::arg("gpuid") = 0,
            py::arg("codec") = musaVideoCodec::musaVideoCodec_H264,
            py::arg("chromaformat") = musaVideoChromaFormat::musaVideoChromaFormat_420,
            py::arg("bitdepth") = 8,
            R"pbdoc(
        Get the capabilities of decoder HW for the given input params
        :param gpuid: GPU Id
        :param codec : Video Codec
        :param chromaformat : Chroma format of the video
        :param bitdepth : Bit-depth of the video
    )pbdoc"
            );

    py::class_<DecodedFrame, std::shared_ptr<DecodedFrame>>(m, "DecodedFrame")
        .def_readonly("timestamp", &DecodedFrame::timestamp)
        .def_readonly("format", &DecodedFrame::format)
        .def_readonly("decoder_stream_event", &DecodedFrame::decoderStreamEvent)
        .def_readonly("decode_stats_ptr", &DecodedFrame::pDecodeStats)
        .def_readonly("decode_stats_size", &DecodedFrame::decodeStatsSize)
        .def("__repr__",
            [](std::shared_ptr<DecodedFrame>& self)
            {
                std::stringstream ss;
                ss << "<DecodedFrame [";
                ss << "timestamp=" << self->timestamp;
                ss << ", format=" << py::str(py::cast(self->format));
                ss << ", " << py::str(py::cast(self->views));
                ss << "]>";
                return ss.str();
            })
        .def("getPTS",
            [](std::shared_ptr<DecodedFrame>& self) {
                
                return self->timestamp;
            },
            R"pbdoc(
            return PTS of the decoded frame
            :param None: None
            )pbdoc")
        .def("getSEIMessage",
            [](std::shared_ptr<DecodedFrame>& self) {
                
                return self->seiMessage;
            },
            R"pbdoc(
            return SEI message of the decoded frame
            :param None: None
            )pbdoc")
        .def("getRawDecodeStats",
            [](std::shared_ptr<DecodedFrame>& self) {
                // Return the raw decode stats buffer
                std::vector<uint8_t> decodeStats = {}; // empty vector
                if (self->pDecodeStats && self->decodeStatsSize > 0) {
                    try {
                        // Additional safety: validate pointer and size
                        decodeStats.resize(self->decodeStatsSize);
                        std::memcpy(decodeStats.data(), self->pDecodeStats, self->decodeStatsSize);
                    } catch (const std::exception& e) {
                        // Return empty vector on any error
                        decodeStats.clear();
                    }
                }
                return decodeStats;
            },
            R"pbdoc(
            return raw decode stats buffer of the decoded frame
            :param None: None
            :return: Raw decode statistics buffer as vector of bytes
            )pbdoc")
        .def("ParseDecodeStats",
            [](std::shared_ptr<DecodedFrame>& self) {
                // musify: disabled — MUSA SDK 5.1.0 MUVID headers do not expose MUVIDDECODESTATSHEADER/MUVIDDECODESTATS; see MUSIFY.md Round 2.
                PYNVVC_THROW_ERROR_UNSUPPORTED("Decode statistics are unavailable in MUSA SDK 5.1.0 MUVID headers.", MUSA_ERROR_NOT_SUPPORTED);
                return py::dict();
            },
            R"pbdoc(
            Parse decode statistics directly from the frame's decode stats buffer
            :param None: None
            :return: Tuple of (qp_luma_list, cu_type_list, mv0_x_list, mv0_y_list, mv1_x_list, mv1_y_list, ...)
                     where mv0_x_list, mv0_y_list contain first motion vector components
                     and mv1_x_list, mv1_y_list contain second motion vector components
                     Additional stats may be added at the end for future compatibility
            )pbdoc"
        )
        .def("framesize",
            [](std::shared_ptr<DecodedFrame>& self) {
                int height = self->views.at(0).shape.at(0);
                int width = self->views.at(0).shape.at(1);
                int framesize = width * height * 1.5;
                switch (self->format)
                {
                case Pixel_Format_NV12:
                        break;
                case Pixel_Format_P016:
                    framesize = width * height * 3;
                    break;
                case Pixel_Format_YUV444:
                    framesize = width * height * 3;
                    break;
                case Pixel_Format_YUV444_16Bit:
                    framesize = width * height * 6;
                    break;
                case Pixel_Format_NV16:
                    framesize = width * height * 2;
                    break;
                case Pixel_Format_P216:
                    framesize = width * height * 4;
                    break;
                case Pixel_Format_RGB:
                    framesize = width * height * 3;
                    break;
                case Pixel_Format_RGBP:
                    framesize = width * height * 3;
                    break;
                default:
                    break;
                }
                return framesize;
            },
            R"pbdoc(
            return underlying views which implement MUSA array interface
            :param None: None
            )pbdoc")
        .def("cuda",
            [](std::shared_ptr<DecodedFrame>& self) {
                return self->views;
            },
            R"pbdoc(
            return underlying views which implement MUSA array interface
            :param None: None
            )pbdoc")
            .def("nv12_to_rgb",
                [](std::shared_ptr<DecodedFrame>& self)
                {
                   

                },
                R"pbdoc(
            return RGB NCHW tensor
            :param None: None
            )pbdoc")
         .def("nvcv_image",
             [](std::shared_ptr<DecodedFrame>& self) {
                 // Deprecation warning
                 PyErr_WarnEx(PyExc_DeprecationWarning, 
                     "nvcv_image() is deprecated and will be removed in a future version. "
                     "Please use alternative methods for CV-CUDA tensor conversion.", 1);
                 
                 switch (self->format)
                 {
                     case Pixel_Format_NV12:
                     {
                         
                         size_t width = self->views.at(0).shape[1];
                         size_t height = self->views.at(0).shape[0] * 1.5;
                         MUdeviceptr data = self->views.at(0).data;
                         MUstream stream = self->views.at(0).stream;
                         self->views.clear();
                         self->views.push_back(CAIMemoryView{ { height, width, 1}, {width, 2, 1}, "|u1", reinterpret_cast<size_t>(stream),(data), false }); //hack for cvmusa tensor represenation
                     }
                     break;
                     case Pixel_Format_YUV444:
                     {

                         size_t width = self->views.at(0).shape[1];
                         size_t height = self->views.at(0).shape[0] * 3;
                         MUdeviceptr data = self->views.at(0).data;
                         MUstream stream = self->views.at(0).stream;
                         self->views.clear();
                         self->views.push_back(CAIMemoryView{ { height, width, 1}, {width, 3, 1}, "|u1", reinterpret_cast<size_t>(stream),(data), false }); //hack for cvmusa tensor represenation
                     }
                break;
             default:
                PYNVVC_THROW_ERROR_UNSUPPORTED("only nv12 and yuv444 supported as of now", MUSA_ERROR_NOT_SUPPORTED);
                break;
                 }
                 return self->views;
             },
             R"pbdoc(
            **DEPRECATED**: This method is deprecated and will be removed in a future version.
            Please use alternative methods for CV-CUDA tensor conversion.
            
            Return underlying views which implement MUSA array interface for CV-CUDA tensor representation.
            Currently supports NV12 and YUV444 formats only.

            :param None: None
            :return: MUSA array interface memory views compatible with CV-CUDA tensors
            
            .. deprecated:: 
               The nvcv_image() method is deprecated. Use alternative tensor conversion methods.
            )pbdoc")

            // DL Pack Tensor
             .def_property_readonly("shape", [](std::shared_ptr<DecodedFrame>& self) {
                return self->extBuf->shape();
                    }, "Get the shape of the buffer as an array")
             .def_property_readonly("strides", [](std::shared_ptr<DecodedFrame>& self) {
                return self->extBuf->strides();
                 }, "Get the strides of the buffer")
             .def_property_readonly("dtype", [](std::shared_ptr<DecodedFrame>& self) {
                return self->extBuf->dtype();
                 }, "Get the data type of the buffer")
             .def("__dlpack__", [](std::shared_ptr<DecodedFrame>& self, py::object stream) {
                return self->extBuf->dlpack(stream, reinterpret_cast<MUstream>(self->decoderStream), reinterpret_cast<MUevent>(self->decoderStreamEvent));
                    }, py::arg("stream") = NULL, "Export the buffer as a DLPack tensor")
             .def("__dlpack_device__", [](std::shared_ptr<DecodedFrame>& self) {
                return self->extBuf->dlpackDevice();
                 }, "Get the device associated with the buffer")
            
            
            .def("GetPtrToPlane",

                [](std::shared_ptr<DecodedFrame>& self, int planeIdx) {
                    return self->views[planeIdx].data;
                    }, R"pbdoc(
            return pointer to base address for plane index
            :param planeIdx : index to the plane
            )pbdoc");
            py::class_<CAIMemoryView, std::shared_ptr<CAIMemoryView>>(m, "CAIMemoryView")
                .def(py::init<std::vector<size_t>, std::vector<size_t>, std::string, size_t, MUdeviceptr, bool>())
                .def_readonly("shape", &CAIMemoryView::shape)
                .def_readonly("stride", &CAIMemoryView::stride)
                .def_readonly("dataptr", &CAIMemoryView::data)
                .def("__repr__",
                    [](std::shared_ptr<CAIMemoryView>& self)
                    {
                        std::stringstream ss;
                        ss << "<CAIMemoryView ";
                        ss << py::str(py::cast(self->shape));
                        ss << ">";
                        return ss.str();
                    })
                .def_readonly("data", &CAIMemoryView::data)
                        .def_property_readonly("__musa_array_interface__",
                            [](std::shared_ptr<CAIMemoryView>& self)
                            {
                                py::dict dict;
                                dict["version"] = 3;
                                dict["shape"] = self->shape;
                                dict["strides"] = self->stride;
                                dict["typestr"] = self->typestr;
                                dict["stream"] = self->stream == 0 ? int(size_t(self->stream)) : 2;
                                dict["data"] = std::make_pair(self->data, false);
                                dict["gpuIdx"] = 0;
                                return dict;
                            });

                    
                    pyNvDecoder
                        .def(py::init<>(),
                            R"pbdoc(
        Constructor method. Initialize decoder with set of particular
        parameters
        :param None: None
    )pbdoc")
                        .def_static("SetSessionCount",
                            [](int numThreads)
                            {
                                return PyMuvidDecoder::SetSessionCount(numThreads);

                            })
                                .def("GetSessionInitTime",
                                    [](std::shared_ptr<PyMuvidDecoder>& dec)
                                    {
                                        return dec->GetSessionInitTime();

                                    })
                                .def("setDecoderSessionID",
                                    [](std::shared_ptr<PyMuvidDecoder>& dec, int sessionID)
                                    {
                                        dec->setDecoderSessionID(sessionID);
                                        
                                    })
                                .def_static("getDecoderSessionOverHead",
                                    [](int sessionID)
                                    {
                                       return PyMuvidDecoder::getDecoderSessionOverHead(sessionID);
                                    })
                                .def("GetPixelFormat",
                                    [](std::shared_ptr<PyMuvidDecoder>& dec)
                                    {
                                        return GetNativeFormat(dec->GetOutputFormat());
                                    },R"pbdoc(
            Returns Pixel format string representation 
            :param None
            :return: String representation of pixel format is returned
    )pbdoc")
                                        .def(
                                            "GetNumDecodedFrame",
                                            [](std::shared_ptr<PyMuvidDecoder>& dec, const PacketData& packetData)
                                            {
                                                return dec->GetNumDecodedFrame(packetData);
                                            }, R"pbdoc(
             Decodes bistream data in Packet into uncompressed data 
            :param PacketData: PacketData Structure
            :return: count of the decoded frames
    )pbdoc"
                                                )
                                        .def(
                                            "GetLockedFrame",
                                            [](std::shared_ptr<PyMuvidDecoder>& dec)
                                            {
                                                uint8_t* pFrame = dec->GetLockedFrame(NULL);
                                                return (MUdeviceptr)pFrame;
                                            }, R"pbdoc(
            This function decodes a frame and returns the locked frame buffers
            This makes the buffers available for use by the application without the buffers
            getting overwritten, even if subsequent decode calls are made. The frame buffers
            remain locked, until UnlockFrame() is called
            :param NULL
            :return: returns decodedFrame from internal buffer
    )pbdoc"
                                                )
                                            .def(
                                                "GetFrame",
                                                [](std::shared_ptr<PyMuvidDecoder>& dec)
                                                {
                                                    return dec->GetFrame();
                                                }, R"pbdoc(
            This function decodes a frame and returns the locked frame buffers
            This makes the buffers available for use by the application without the buffers
            getting overwritten, even if subsequent decode calls are made. The frame buffers
            remain locked, until UnlockFrame() is called
            :param NULL
            :return: returns decodedFrame from internal buffer
    )pbdoc"
                                                )
                                        .def(
                                            "UnlockFrame",
                                            [](std::shared_ptr<PyMuvidDecoder>& dec, MUdeviceptr pFrame)
                                            {
                                                return dec->UnlockFrame((uint8_t*)pFrame);
                                            }, R"pbdoc(
            This function unlocks the frame buffer and makes the frame buffers available for write again
            :param NULL
            :return: void
    )pbdoc"
                                                )
                                        .def(
                                            "Decode",
                                            [](std::shared_ptr<PyMuvidDecoder>& dec, const PacketData& packetData)
                                            {
                                                return dec->Decode(packetData);
                                            }, R"pbdoc(
            Decodes bistream data in Packet into uncompressed data 
            :param PacketData: PacketData Structure
            :return: uncompressed data is returned as List of Decoded Frames
    )pbdoc"
                                                )
                        .def(
                            "SetSeekPTS",
                            [](std::shared_ptr<PyMuvidDecoder>& dec, const int64_t targetPTS)
                            {
                                return dec->setSeekPTS(targetPTS);
                            }, R"pbdoc(
             sets PTS of of the target frame to search 
            :param PacketData: PacketData Structure
            :return: uncompressed data is returned as List of Decoded Frames
    )pbdoc"
                                )
                                .def(
                                    "Decode",
                                    [](std::shared_ptr<PyMuvidDecoder>& dec, const PacketData& packetData)
                                    {
                                        return dec->Decode(packetData);
                                    }, R"pbdoc(
            Decodes bistream data in Packet into uncompressed data 
            :param PacketData: PacketData Structure
            :return: uncompressed data is returned as List of Decoded Frames
            )pbdoc"
            )
                        .def(
                            "setReconfigParams",
                            [](std::shared_ptr<PyMuvidDecoder>& dec, int width, int height)
                            {
                                Dim resizedim = { 0 };
                                resizedim.w = width;
                                resizedim.h = height;
                                return dec->setReconfigParams(resizedim);
                            },

                            py::arg("width") = 0,
                            py::arg("height") = 0,

                            R"pbdoc(
        This function allows app to set decoder reconfig params
        :param width : updated width set by application for the decoded surface
        :param height : updated height set by application for the decoded surface
    )pbdoc"
                        )
                
                .def(
                "GetWidth",
                [](std::shared_ptr<PyMuvidDecoder>& dec)
                {
                    return dec->GetWidth();
                },R"pbdoc()pbdoc"
                "Get the width of decoded frame"
                )
                .def(
                "GetHeight",
                [](std::shared_ptr<PyMuvidDecoder>& dec)
                {
                    return dec->GetHeight();
                },R"pbdoc()pbdoc"
                "Get the height of decoded frame"
                )
                .def(
                "GetFrameSize",
                [](std::shared_ptr<PyMuvidDecoder>& dec)
                {
                    return dec->GetFrameSize();
                },R"pbdoc()pbdoc"
                "Get the size of decoded frame"
                )
 
                .def(
                "WaitOnCUStream",
                [](std::shared_ptr<PyMuvidDecoder>& dec, size_t _stream)
                {
                    return dec->CUStreamWaitOnEvent(reinterpret_cast<MUstream>(_stream));
                }, R"pbdoc(
                Wait for post proc kernels + memcopy to finish so that input stream can access it
                :param application created stream
                :return: None
                )pbdoc"
                )
                .def(
                "SyncOnCUStream",
                [](std::shared_ptr<PyMuvidDecoder>& dec)
                {
                    return dec->CUStreamSyncOnEvent();
                }, R"pbdoc(
                Sync forces post proc kernels + memcopy to finish so that any stream can access it
                :param None
                :return: None
                )pbdoc"
                )
                .def(
                "__iter__",
                [](shared_ptr<PyMuvidDecoder> self) {
                    return self;
                },
                R"pbdoc(
                Iterator over decoder object
                )pbdoc"
                )
                .def(
                "__next__",
                [](shared_ptr<PyMuvidDecoder> self, const PacketData& packetData) {

                    if (packetData.bsl != 0)
                    {
                        return self->Decode(packetData);
                    }
                    else
                    {
                        throw py::stop_iteration();
                    }

                },
                R"pbdoc(
                gets the next element in Iterator over decoder object
                )pbdoc");
}
