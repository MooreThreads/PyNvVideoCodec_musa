/*
 * This copyright notice applies to this header file only:
 *
 * Copyright (c) 2010-2026 NVIDIA Corporation
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

#include "configNvEncVer.h"


#ifdef MTENC_VER_13_0

#include "MtEncoder/MtEncoder_130.h"

#ifndef _WIN32
#ifndef BOOLEAN_OPERATOR_EQ_GUID
#define BOOLEAN_OPERATOR_EQ_GUID
#include <cstring>
#include <cstdlib>
static inline bool operator==(const GUID &guid1, const GUID &guid2) {
    return !memcmp(&guid1, &guid2, sizeof(GUID));
}

static inline bool operator!=(const GUID &guid1, const GUID &guid2) {
    return !(guid1 == guid2);
}
#endif
#endif
MtEncoder::MtEncoder(MT_ENC_DEVICE_TYPE eDeviceType, void *pDevice, uint32_t nWidth, uint32_t nHeight, MT_ENC_BUFFER_FORMAT eBufferFormat,
                            uint32_t nExtraOutputDelay, bool bMotionEstimationOnly, bool bOutputInVideoMemory, bool bDX12Encode, bool bUseIVFContainer,
                            bool bRepeatSequenceHeader) :
    m_pDevice(pDevice), 
    m_eDeviceType(eDeviceType),
    m_nWidth(nWidth),
    m_nHeight(nHeight),
    m_nMaxEncodeWidth(nWidth),
    m_nMaxEncodeHeight(nHeight),
    m_eBufferFormat(eBufferFormat), 
    m_bMotionEstimationOnly(bMotionEstimationOnly), 
    m_bOutputInVideoMemory(bOutputInVideoMemory),
    m_bIsDX12Encode(bDX12Encode),
    m_bUseIVFContainer(bUseIVFContainer),
    m_nExtraOutputDelay(nExtraOutputDelay), 
    m_bRepeatSequenceHeader(bRepeatSequenceHeader),
    m_hEncoder(nullptr)
{
    LoadNvEncApi();

    if (!m_nvenc.mtEncOpenEncodeSession) 
    {
        m_nEncoderBuffer = 0;
        PYNVVC_THROW_ERROR("EncodeAPI not found", MT_ENC_ERR_NO_ENCODE_DEVICE);
    }

    MT_ENC_OPEN_ENCODE_SESSION_EX_PARAMS encodeSessionExParams = { MT_ENC_OPEN_ENCODE_SESSION_EX_PARAMS_VER };
    encodeSessionExParams.device = m_pDevice;
    encodeSessionExParams.deviceType = m_eDeviceType;
    encodeSessionExParams.apiVersion = MTENCAPI_VERSION;
    void *hEncoder = NULL;
    MTENC_API_CALL(m_nvenc.mtEncOpenEncodeSessionEx(&encodeSessionExParams, &hEncoder));
    m_hEncoder = hEncoder;
}

void MtEncoder::LoadNvEncApi()
{
#if defined(_WIN32)
#if defined(_WIN64)
    HMODULE hModule = LoadLibrary(TEXT("mtEncodeAPI64.dll"));
#else
    HMODULE hModule = LoadLibrary(TEXT("mtEncodeAPI.dll"));
#endif
#else
    void* hModule = dlopen("/usr/local/pynvc_enc_only/libencode_musa.so.13.0", RTLD_LAZY);
    if (!hModule) {
        hModule = dlopen("libencode_musa.so", RTLD_LAZY);
    }
#endif

    if (hModule == nullptr) {
        PYNVVC_THROW_ERROR(
            "MTENC library file is not found. Please ensure NV driver is installed",
            MT_ENC_ERR_NO_ENCODE_DEVICE);
    }

    m_hModule = hModule;

    typedef MTENCSTATUS(MTENCAPI*
        MtEncodeAPIGetMaxSupportedVersion_Type)(uint32_t*);
#if defined(_WIN32)
    auto MtEncodeAPIGetMaxSupportedVersion =
        (MtEncodeAPIGetMaxSupportedVersion_Type)GetProcAddress(
            hModule, "MtEncodeAPIGetMaxSupportedVersion");
#else
    auto MtEncodeAPIGetMaxSupportedVersion =
        (MtEncodeAPIGetMaxSupportedVersion_Type)dlsym(
            hModule, "MtEncodeAPIGetMaxSupportedVersion");
#endif

    uint32_t version = 0;
    uint32_t currentVersion = (MTENCAPI_MAJOR_VERSION << 4) | MTENCAPI_MINOR_VERSION;
    MTENC_API_CALL(MtEncodeAPIGetMaxSupportedVersion(&version));
    if (currentVersion > version)
    {
        PYNVVC_THROW_ERROR("Current Driver Version does not support this NvEncodeAPI version, please upgrade driver", MT_ENC_ERR_INVALID_VERSION);
    }

    typedef MTENCSTATUS(MTENCAPI* MtEncodeAPICreateInstance_Type)(
        MT_ENCODE_API_FUNCTION_LIST*);
#if defined(_WIN32)
    auto MtEncodeAPICreateInstance =
        (MtEncodeAPICreateInstance_Type)GetProcAddress(
            hModule, "MtEncodeAPICreateInstance");
#else
    auto MtEncodeAPICreateInstance = (MtEncodeAPICreateInstance_Type)dlsym(
        hModule, "MtEncodeAPICreateInstance");
#endif

    if (!MtEncodeAPICreateInstance) {
        PYNVVC_THROW_ERROR(
            "Cannot find MtEncodeAPICreateInstance() entry in MTENC library",
            MT_ENC_ERR_NO_ENCODE_DEVICE);
    }

    m_nvenc = { MT_ENCODE_API_FUNCTION_LIST_VER };
    MTENC_API_CALL(MtEncodeAPICreateInstance(&m_nvenc));
}

MtEncoder::~MtEncoder()
{
    DestroyHWEncoder();
    if (m_hModule) {
#if defined(_WIN32)
        FreeLibrary((HMODULE)m_hModule);
#else
        dlclose(m_hModule);
#endif
        m_hModule = nullptr;
    }
}

void MtEncoder::CreateDefaultEncoderParams(MT_ENC_INITIALIZE_PARAMS* pIntializeParams, GUID codecGuid, GUID presetGuid, MT_ENC_TUNING_INFO tuningInfo)
{
    if (!m_hEncoder)
    {
        PYNVVC_THROW_ERROR("Encoder Initialization failed", MT_ENC_ERR_NO_ENCODE_DEVICE);
        return;
    }

    if (pIntializeParams == nullptr || pIntializeParams->encodeConfig == nullptr)
    {
        PYNVVC_THROW_ERROR("pInitializeParams and pInitializeParams->encodeConfig can't be NULL", MT_ENC_ERR_INVALID_PTR);
    }

    memset(pIntializeParams->encodeConfig, 0, sizeof(MT_ENC_CONFIG));
    auto pEncodeConfig = pIntializeParams->encodeConfig;
    memset(pIntializeParams, 0, sizeof(MT_ENC_INITIALIZE_PARAMS));
    pIntializeParams->encodeConfig = pEncodeConfig;


    pIntializeParams->encodeConfig->version = MT_ENC_CONFIG_VER;
    pIntializeParams->version = MT_ENC_INITIALIZE_PARAMS_VER;

    pIntializeParams->encodeGUID = codecGuid;
    pIntializeParams->presetGUID = presetGuid;
    pIntializeParams->encodeWidth = m_nWidth;
    pIntializeParams->encodeHeight = m_nHeight;
    pIntializeParams->darWidth = m_nWidth;
    pIntializeParams->darHeight = m_nHeight;
    pIntializeParams->frameRateNum = 30;
    pIntializeParams->frameRateDen = 1;
    pIntializeParams->enablePTD = 1;
    pIntializeParams->reportSliceOffsets = 0;
    pIntializeParams->enableSubFrameWrite = 0;
    pIntializeParams->maxEncodeWidth = m_nWidth;
    pIntializeParams->maxEncodeHeight = m_nHeight;
    pIntializeParams->enableMEOnlyMode = m_bMotionEstimationOnly;
    pIntializeParams->enableOutputInVidmem = m_bOutputInVideoMemory;
#if defined(_WIN32)
    if (!m_bOutputInVideoMemory)
    {
        pIntializeParams->enableEncodeAsync = GetCapabilityValue(codecGuid, MT_ENC_CAPS_ASYNC_ENCODE_SUPPORT);
    }
#endif

    pIntializeParams->tuningInfo = tuningInfo;
    pIntializeParams->encodeConfig->rcParams.rateControlMode = MT_ENC_PARAMS_RC_CONSTQP;

    //There are changes in the structure layout, therefore users are recommended to be careful while moving their application to the new header. 
    //Following initialization has changed for the same reason.
    MT_ENC_PRESET_CONFIG presetConfig = { MT_ENC_PRESET_CONFIG_VER, 0, { MT_ENC_CONFIG_VER } };
    m_nvenc.mtEncGetEncodePresetConfigEx(m_hEncoder, codecGuid, presetGuid, tuningInfo, &presetConfig);
    memcpy(pIntializeParams->encodeConfig, &presetConfig.presetCfg, sizeof(MT_ENC_CONFIG));


    if(m_bMotionEstimationOnly)
    {
        m_encodeConfig.version = MT_ENC_CONFIG_VER;
        m_encodeConfig.rcParams.rateControlMode = MT_ENC_PARAMS_RC_CONSTQP;
        m_encodeConfig.rcParams.constQP = { 28, 31, 25 };
    }
    
    if (pIntializeParams->encodeGUID == MT_ENC_CODEC_H264_GUID)
    {
        if (m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV444 || m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV444_10BIT)
        {
            pIntializeParams->encodeConfig->encodeCodecConfig.h264Config.chromaFormatIDC = 3;
        }
        // musify: disabled — SDK 5.1.0 mtEncodeAPI.h does not expose MT_ENC_BUFFER_FORMAT_NV16; keep P210 4:2:2 handling.
        else if (m_eBufferFormat == MT_ENC_BUFFER_FORMAT_P210)
        {
            pIntializeParams->encodeConfig->encodeCodecConfig.h264Config.chromaFormatIDC = 2;
        }
        pIntializeParams->encodeConfig->encodeCodecConfig.h264Config.idrPeriod = pIntializeParams->encodeConfig->gopLength;
    }
    else if (pIntializeParams->encodeGUID == MT_ENC_CODEC_HEVC_GUID)
    {
        pIntializeParams->encodeConfig->encodeCodecConfig.hevcConfig.inputBitDepth = pIntializeParams->encodeConfig->encodeCodecConfig.hevcConfig.outputBitDepth =
            (m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV420_10BIT || m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV444_10BIT ) ? MT_ENC_BIT_DEPTH_10 : MT_ENC_BIT_DEPTH_8;
        if (m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV444 || m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV444_10BIT)
        {
            pIntializeParams->encodeConfig->encodeCodecConfig.hevcConfig.chromaFormatIDC = 3;
        }
        // musify: disabled — SDK 5.1.0 mtEncodeAPI.h does not expose MT_ENC_BUFFER_FORMAT_NV16; keep P210 4:2:2 handling.
        else if (m_eBufferFormat == MT_ENC_BUFFER_FORMAT_P210)
        {
            pIntializeParams->encodeConfig->encodeCodecConfig.hevcConfig.chromaFormatIDC = 2;
        }
        pIntializeParams->encodeConfig->encodeCodecConfig.hevcConfig.idrPeriod = pIntializeParams->encodeConfig->gopLength;
    }
    else if (pIntializeParams->encodeGUID == MT_ENC_CODEC_AV1_GUID)
    {
		pIntializeParams->encodeConfig->encodeCodecConfig.av1Config.inputBitDepth = (m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV420_10BIT) ? MT_ENC_BIT_DEPTH_10 : MT_ENC_BIT_DEPTH_8;
        pIntializeParams->encodeConfig->encodeCodecConfig.av1Config.chromaFormatIDC = 1;
        pIntializeParams->encodeConfig->encodeCodecConfig.av1Config.idrPeriod = pIntializeParams->encodeConfig->gopLength;
        if (m_bRepeatSequenceHeader)
        {
            pIntializeParams->encodeConfig->encodeCodecConfig.av1Config.disableSeqHdr = 0;
            pIntializeParams->encodeConfig->encodeCodecConfig.av1Config.repeatSeqHdr = 1;
        }
        if (m_bOutputInVideoMemory)
        {
            pIntializeParams->encodeConfig->frameIntervalP = 1;
        }
    }

    if (m_bIsDX12Encode)
    {
        pIntializeParams->bufferFormat = m_eBufferFormat;
    }
    
    return;
}

void MtEncoder::CreateEncoder(const MT_ENC_INITIALIZE_PARAMS* pEncoderParams)
{
    if (!m_hEncoder)
    {
        PYNVVC_THROW_ERROR("Encoder Initialization failed", MT_ENC_ERR_NO_ENCODE_DEVICE);
    }

    if (!pEncoderParams)
    {
        PYNVVC_THROW_ERROR("Invalid MT_ENC_INITIALIZE_PARAMS ptr", MT_ENC_ERR_INVALID_PTR);
    }

    if (pEncoderParams->encodeWidth == 0 || pEncoderParams->encodeHeight == 0)
    {
        PYNVVC_THROW_ERROR("Invalid encoder width and height", MT_ENC_ERR_INVALID_PARAM);
    }

    if (pEncoderParams->encodeGUID != MT_ENC_CODEC_H264_GUID && pEncoderParams->encodeGUID != MT_ENC_CODEC_HEVC_GUID && pEncoderParams->encodeGUID != MT_ENC_CODEC_AV1_GUID)
    {
        std::ostringstream errorString;
        errorString << "Invalid codec guid" << std::endl
                    << "Supported GUIDs : " << std::endl
                    << "  " << MAKE_STRING(MT_ENC_CODEC_H264_GUID) << std::endl
                    << "  " << MAKE_STRING(MT_ENC_CODEC_HEVC_GUID) << std::endl
                    << "  " << MAKE_STRING(MT_ENC_CODEC_AV1_GUID);

        const std::string cErr = errorString.str();
        PYNVVC_THROW_ERROR_UNSUPPORTED(cErr, MT_ENC_ERR_INVALID_PARAM);
    }

    if (pEncoderParams->encodeGUID == MT_ENC_CODEC_AV1_GUID)
    {
        if (m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV444 || m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV444_10BIT)
        {
            std::ostringstream errorString;
            errorString << "YUV444 format isn't supported by AV1 encoder" << std::endl
                        << "Unsupported buffer format : " << m_eBufferFormat;

            const std::string cErr = errorString.str();
            PYNVVC_THROW_ERROR_UNSUPPORTED(cErr, MT_ENC_ERR_INVALID_PARAM);
        }
    }
	
    // set other necessary params if not set yet
    if (pEncoderParams->encodeGUID == MT_ENC_CODEC_H264_GUID)
    {
        bool yuv10BitFormat = (m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV420_10BIT || m_eBufferFormat == MT_ENC_BUFFER_FORMAT_P210 || m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV444_10BIT) ? true : false;
        if (yuv10BitFormat && pEncoderParams->encodeConfig->encodeCodecConfig.h264Config.inputBitDepth != MT_ENC_BIT_DEPTH_10)
        {

            std::ostringstream errorString;
            errorString << "10-bit format isn't supported by H264 encoder" << std::endl
                        << "Unsupported buffer format : " << m_eBufferFormat;

            const std::string cErr = errorString.str();
            PYNVVC_THROW_ERROR_UNSUPPORTED(cErr, MT_ENC_ERR_INVALID_PARAM);
        }
		
		if ((m_eBufferFormat == MT_ENC_BUFFER_FORMAT_P210) &&
            (pEncoderParams->encodeConfig->encodeCodecConfig.h264Config.chromaFormatIDC != 2))
        {
            std::ostringstream errorString;
            errorString << "Invalid ChromaFormatIDC" << std::endl
                        << "Buffer format : " << MAKE_STRING(MT_ENC_BUFFER_FORMAT_YUV444) << std::endl
                        << "Unsupported ChromaFormatIDC : " << pEncoderParams->encodeConfig->encodeCodecConfig.h264Config.chromaFormatIDC << std::endl
                        << "Supported ChromaFormatIDC   : " << 2;

            const std::string cErr = errorString.str();
            PYNVVC_THROW_ERROR_UNSUPPORTED(cErr, MT_ENC_ERR_INVALID_PARAM);
        }

        if ((m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV444) &&
            (pEncoderParams->encodeConfig->encodeCodecConfig.h264Config.chromaFormatIDC != 3))
        {
            std::ostringstream errorString;
            errorString << "Invalid ChromaFormatIDC" << std::endl
                        << "Buffer format : " << MAKE_STRING(MT_ENC_BUFFER_FORMAT_YUV444) << std::endl
                        << "Unsupported ChromaFormatIDC : " << pEncoderParams->encodeConfig->encodeCodecConfig.h264Config.chromaFormatIDC << std::endl
                        << "Supported ChromaFormatIDC   : " << 3;

            const std::string cErr = errorString.str();
            PYNVVC_THROW_ERROR_UNSUPPORTED(cErr, MT_ENC_ERR_INVALID_PARAM);
        }
        if (pEncoderParams->encodeConfig->frameIntervalP == 4)
        {
            pEncoderParams->encodeConfig->encodeCodecConfig.h264Config.useBFramesAsRef = MT_ENC_BFRAME_REF_MODE_MIDDLE;//forcing B frame to be middle reference frames only for h264
            m_bBRefMiddleForced = true;
        }
    }

    if (pEncoderParams->encodeGUID == MT_ENC_CODEC_HEVC_GUID)
    {
        bool yuv10BitFormat = (m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV420_10BIT || m_eBufferFormat == MT_ENC_BUFFER_FORMAT_P210 || m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV444_10BIT) ? true : false;
        if (yuv10BitFormat && pEncoderParams->encodeConfig->encodeCodecConfig.hevcConfig.inputBitDepth != MT_ENC_BIT_DEPTH_10)
        {
            PYNVVC_THROW_ERROR_UNSUPPORTED("Invalid PixelBitdepth", MT_ENC_ERR_INVALID_PARAM);
        }

        if ((m_eBufferFormat == MT_ENC_BUFFER_FORMAT_P210) &&
            (pEncoderParams->encodeConfig->encodeCodecConfig.hevcConfig.chromaFormatIDC != 2))
        {
            PYNVVC_THROW_ERROR_UNSUPPORTED("Invalid ChromaFormatIDC", MT_ENC_ERR_INVALID_PARAM);
        }

        if ((m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV444 || m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV444_10BIT) &&
            (pEncoderParams->encodeConfig->encodeCodecConfig.hevcConfig.chromaFormatIDC != 3))
        {
            std::ostringstream errorString;
            errorString << "Invalid ChromaFormatIDC" << std::endl
                        << "Unsupported ChromaFormatIDC : " << pEncoderParams->encodeConfig->encodeCodecConfig.hevcConfig.chromaFormatIDC << std::endl
                        << "Supported ChromaFormatIDC   : " << 3;

            const std::string cErr = errorString.str();
            PYNVVC_THROW_ERROR_UNSUPPORTED(cErr, MT_ENC_ERR_INVALID_PARAM);
        }
        if (pEncoderParams->encodeConfig->frameIntervalP == 4)
        {
            pEncoderParams->encodeConfig->encodeCodecConfig.hevcConfig.useBFramesAsRef = MT_ENC_BFRAME_REF_MODE_MIDDLE;//forcing B frame to be middle reference frames only for h264
            m_bBRefMiddleForced = true;
        }
    }

    if (pEncoderParams->encodeGUID == MT_ENC_CODEC_AV1_GUID)
    {
        bool yuv10BitFormat = (m_eBufferFormat == MT_ENC_BUFFER_FORMAT_YUV420_10BIT) ? true : false;
        if (yuv10BitFormat && pEncoderParams->encodeConfig->encodeCodecConfig.av1Config.inputBitDepth != MT_ENC_BIT_DEPTH_10)
        {
            PYNVVC_THROW_ERROR_UNSUPPORTED("Invalid PixelBitdepth", MT_ENC_ERR_INVALID_PARAM);
        }

        if (pEncoderParams->encodeConfig->encodeCodecConfig.av1Config.chromaFormatIDC != 1)
        {
            std::ostringstream errorString;
            errorString << "Invalid ChromaFormatIDC" << std::endl
                        << "Unsupported ChromaFormatIDC : " << pEncoderParams->encodeConfig->encodeCodecConfig.av1Config.chromaFormatIDC << std::endl
                        << "Supported ChromaFormatIDC   : " << 1;

            const std::string cErr = errorString.str();
            PYNVVC_THROW_ERROR_UNSUPPORTED(cErr, MT_ENC_ERR_INVALID_PARAM);
        }

        if (m_bOutputInVideoMemory && pEncoderParams->encodeConfig->frameIntervalP > 1)
        {
            PYNVVC_THROW_ERROR_UNSUPPORTED("Alt Ref frames not supported for AV1 in case of OutputInVideoMemory", MT_ENC_ERR_INVALID_PARAM);
        }
        if (pEncoderParams->encodeConfig->frameIntervalP == 4)
        {
            pEncoderParams->encodeConfig->encodeCodecConfig.av1Config.useBFramesAsRef = MT_ENC_BFRAME_REF_MODE_MIDDLE;//forcing B frame to be middle reference frames only for h264
            m_bBRefMiddleForced = true;
        }
    }

    memcpy(&m_initializeParams, pEncoderParams, sizeof(m_initializeParams));
    m_initializeParams.version = MT_ENC_INITIALIZE_PARAMS_VER;

    if (pEncoderParams->encodeConfig)
    {
        memcpy(&m_encodeConfig, pEncoderParams->encodeConfig, sizeof(m_encodeConfig));
        m_encodeConfig.version = MT_ENC_CONFIG_VER;
    }
    else
    {
        //There are changes in the structure layout, therefore users are recommended to be careful while moving their application to the new header. 
        //Following initialization has changed for the same reason.
        MT_ENC_PRESET_CONFIG presetConfig = { MT_ENC_PRESET_CONFIG_VER, 0, { MT_ENC_CONFIG_VER } };
        if (!m_bMotionEstimationOnly)
        {
            m_nvenc.mtEncGetEncodePresetConfigEx(m_hEncoder, pEncoderParams->encodeGUID, pEncoderParams->presetGUID, pEncoderParams->tuningInfo, &presetConfig);
            memcpy(&m_encodeConfig, &presetConfig.presetCfg, sizeof(MT_ENC_CONFIG));
            if (m_bOutputInVideoMemory && pEncoderParams->encodeGUID == MT_ENC_CODEC_AV1_GUID)
            {
                m_encodeConfig.frameIntervalP = 1;
            }
        }
        else
        {
            m_encodeConfig.version = MT_ENC_CONFIG_VER;
            m_encodeConfig.rcParams.rateControlMode = MT_ENC_PARAMS_RC_CONSTQP;
            m_encodeConfig.rcParams.constQP = { 28, 31, 25 };
        }
    }

    if (((uint32_t)m_encodeConfig.frameIntervalP) > m_encodeConfig.gopLength)
    {
        m_encodeConfig.frameIntervalP = m_encodeConfig.gopLength;
    }

    m_initializeParams.encodeConfig = &m_encodeConfig;



    {
        MTENCSTATUS initStatus = m_nvenc.mtEncInitializeEncoder(m_hEncoder, &m_initializeParams);
        // The B-frames-as-reference MIDDLE mode and two-pass encoding are not
        // supported by all MTENC driver versions (both return
        // MT_ENC_ERR_UNSUPPORTED_PARAM). The SDK docs ask clients to check the
        // corresponding caps, but those caps enums are not defined in the
        // 5.1.0 headers, so probe by retrying once with the unsupported
        // features disabled.
        if (initStatus == MT_ENC_ERR_UNSUPPORTED_PARAM)
        {
            bool retry = false;
            if (m_bBRefMiddleForced)
            {
                LOG(WARNING) << "mtEncInitializeEncoder rejected B-frames-as-ref "
                                "MIDDLE mode; retrying with B-ref disabled\n";
                if (pEncoderParams->encodeGUID == MT_ENC_CODEC_H264_GUID)
                {
                    m_encodeConfig.encodeCodecConfig.h264Config.useBFramesAsRef =
                        MT_ENC_BFRAME_REF_MODE_DISABLED;
                }
                else if (pEncoderParams->encodeGUID == MT_ENC_CODEC_HEVC_GUID)
                {
                    m_encodeConfig.encodeCodecConfig.hevcConfig.useBFramesAsRef =
                        MT_ENC_BFRAME_REF_MODE_DISABLED;
                }
                else if (pEncoderParams->encodeGUID == MT_ENC_CODEC_AV1_GUID)
                {
                    m_encodeConfig.encodeCodecConfig.av1Config.useBFramesAsRef =
                        MT_ENC_BFRAME_REF_MODE_DISABLED;
                }
                retry = true;
            }
            if (m_encodeConfig.rcParams.multiPass != MT_ENC_MULTI_PASS_DISABLED)
            {
                LOG(WARNING) << "mtEncInitializeEncoder rejected two-pass "
                                "encoding; retrying with multipass disabled\n";
                m_encodeConfig.rcParams.multiPass = MT_ENC_MULTI_PASS_DISABLED;
                retry = true;
            }
            if (retry)
            {
                initStatus = m_nvenc.mtEncInitializeEncoder(m_hEncoder, &m_initializeParams);
            }
        }
        MTENC_API_CALL(initStatus);
    }

    m_bEncoderInitialized = true;
    m_nWidth = m_initializeParams.encodeWidth;
    m_nHeight = m_initializeParams.encodeHeight;
    m_nMaxEncodeWidth = m_initializeParams.maxEncodeWidth;
    m_nMaxEncodeHeight = m_initializeParams.maxEncodeHeight;

    m_nEncoderBuffer = m_encodeConfig.frameIntervalP + m_encodeConfig.rcParams.lookaheadDepth + m_nExtraOutputDelay;

    if (pEncoderParams->encodeGUID == MT_ENC_CODEC_HEVC_GUID)
    {
        m_enableStereoMVHEVC = m_initializeParams.encodeConfig->encodeCodecConfig.hevcConfig.enableMVHEVC;
        if (m_enableStereoMVHEVC)
        {
            m_nEncoderBuffer = m_nEncoderBuffer * 2;
            m_outputHevc3DReferenceDisplayInfo = m_initializeParams.encodeConfig->encodeCodecConfig.hevcConfig.outputHevc3DReferenceDisplayInfo;
        }
    }

    m_nOutputDelay = m_nEncoderBuffer - 1;

    if (!m_bOutputInVideoMemory)
    {
        m_vpCompletionEvent.resize(m_nEncoderBuffer, nullptr);
    }

#if defined(_WIN32)
    for (uint32_t i = 0; i < m_vpCompletionEvent.size(); i++) 
    {
        m_vpCompletionEvent[i] = CreateEvent(NULL, FALSE, FALSE, NULL);
        if (!m_bIsDX12Encode)
        {
            MT_ENC_EVENT_PARAMS eventParams = { MT_ENC_EVENT_PARAMS_VER };
            eventParams.completionEvent = m_vpCompletionEvent[i];
            m_nvenc.mtEncRegisterAsyncEvent(m_hEncoder, &eventParams);
        }
    }
#endif

    m_vMappedInputBuffers.resize(m_nEncoderBuffer, nullptr);

    if (m_bMotionEstimationOnly)
    {
        m_vMappedRefBuffers.resize(m_nEncoderBuffer, nullptr);

        if (!m_bOutputInVideoMemory)
        {
            InitializeMVOutputBuffer();
        }
    }
    else
    {
        if (!m_bOutputInVideoMemory && !m_bIsDX12Encode)
        {
            m_vBitstreamOutputBuffer.resize(m_nEncoderBuffer, nullptr);
            InitializeBitstreamBuffer();
        }
    }

    AllocateInputBuffers(m_nEncoderBuffer);
}

void MtEncoder::DestroyEncoder()
{
    if (!m_hEncoder)
    {
        return;
    }

    ReleaseInputBuffers();

    DestroyHWEncoder();
}

void MtEncoder::DestroyHWEncoder()
{
    if (!m_hEncoder)
    {
        return;
    }

#if defined(_WIN32)
    for (uint32_t i = 0; i < m_vpCompletionEvent.size(); i++)
    {
        if (m_vpCompletionEvent[i])
        {
            if (!m_bIsDX12Encode)
            {
                MT_ENC_EVENT_PARAMS eventParams = { MT_ENC_EVENT_PARAMS_VER };
                eventParams.completionEvent = m_vpCompletionEvent[i];
                m_nvenc.mtEncUnregisterAsyncEvent(m_hEncoder, &eventParams);
            }
            CloseHandle(m_vpCompletionEvent[i]);
        }
    }
    m_vpCompletionEvent.clear();
#endif

    if (m_bMotionEstimationOnly)
    {
        DestroyMVOutputBuffer();
    }
    else
    {
        if (!m_bIsDX12Encode)
            DestroyBitstreamBuffer();
    }

    m_nvenc.mtEncDestroyEncoder(m_hEncoder);

    m_hEncoder = nullptr;

    m_bEncoderInitialized = false;
}

const NvEncInputFrame* MtEncoder::GetNextInputFrame()
{
    int i = m_iToSend % m_nEncoderBuffer;
    return &m_vInputFrames[i];
}

const NvEncInputFrame* MtEncoder::GetNextInputFrame(uint32_t frameIdx) // for external lookahead API in Iterative Encoder sample (AppEncQual)
{
    int i = frameIdx % m_nEncoderBuffer;
    return &m_vInputFrames[i];
}

const NvEncInputFrame* MtEncoder::GetNextReferenceFrame()
{
    int i = m_iToSend % m_nEncoderBuffer;
    return &m_vReferenceFrames[i];
}

void MtEncoder::MapResources(uint32_t bfrIdx)
{
    NVTX_SCOPED_RANGE("MapResources")
    MT_ENC_MAP_INPUT_RESOURCE mapInputResource = { MT_ENC_MAP_INPUT_RESOURCE_VER };

    mapInputResource.registeredResource = m_vRegisteredResources[bfrIdx];
    MTENC_API_CALL(m_nvenc.mtEncMapInputResource(m_hEncoder, &mapInputResource));
    m_vMappedInputBuffers[bfrIdx] = mapInputResource.mappedResource;

    if (m_bMotionEstimationOnly)
    {
        mapInputResource.registeredResource = m_vRegisteredResourcesForReference[bfrIdx];
        MTENC_API_CALL(m_nvenc.mtEncMapInputResource(m_hEncoder, &mapInputResource));
        m_vMappedRefBuffers[bfrIdx] = mapInputResource.mappedResource;
    }
}

void MtEncoder::EncodeFrame(std::vector<NvEncOutputFrame> &vPacket, MT_ENC_PIC_PARAMS *pPicParams)
{
    NVTX_SCOPED_RANGE("EncodeFrame")
    vPacket.clear();
    if (!IsHWEncoderInitialized())
    {
        PYNVVC_THROW_ERROR("Encoder device not found", MT_ENC_ERR_NO_ENCODE_DEVICE);
    }

    int bfrIdx = m_iToSend % m_nEncoderBuffer;

    MapResources(bfrIdx);

    MTENCSTATUS nvStatus = DoEncode(m_vMappedInputBuffers[bfrIdx], m_vBitstreamOutputBuffer[bfrIdx], pPicParams);

    if (nvStatus == MT_ENC_SUCCESS || nvStatus == MT_ENC_ERR_NEED_MORE_INPUT)
    {
        m_iToSend++;
        GetEncodedPacket(m_vBitstreamOutputBuffer, vPacket, true);
    }
    else
    {
        PYNVVC_THROW_ERROR("nvEncEncodePicture API failed", nvStatus);
    }
}


void MtEncoder::RunMotionEstimation(std::vector<uint8_t> &mvData)
{
    if (!m_hEncoder)
    {
        PYNVVC_THROW_ERROR("Encoder Initialization failed", MT_ENC_ERR_NO_ENCODE_DEVICE);
        return;
    }

    const uint32_t bfrIdx = m_iToSend % m_nEncoderBuffer;

    MapResources(bfrIdx);

    MTENCSTATUS nvStatus = DoMotionEstimation(m_vMappedInputBuffers[bfrIdx], m_vMappedRefBuffers[bfrIdx], m_vMVDataOutputBuffer[bfrIdx]);

    if (nvStatus == MT_ENC_SUCCESS)
    {
        m_iToSend++;
        std::vector<NvEncOutputFrame> vPacket;
        GetEncodedPacket(m_vMVDataOutputBuffer, vPacket, true);
        if (vPacket.size() != 1)
        {
            PYNVVC_THROW_ERROR("GetEncodedPacket() doesn't return one (and only one) MVData", MT_ENC_ERR_GENERIC);
        }
        mvData = vPacket[0].frame;
    }
    else
    {
        PYNVVC_THROW_ERROR("nvEncEncodePicture API failed", nvStatus);
    }
}


void MtEncoder::GetSequenceParams(std::vector<uint8_t> &seqParams)
{
    uint8_t spsppsData[1024]; // Assume maximum spspps data is 1KB or less
    memset(spsppsData, 0, sizeof(spsppsData));
    MT_ENC_SEQUENCE_PARAM_PAYLOAD payload = { MT_ENC_SEQUENCE_PARAM_PAYLOAD_VER };
    uint32_t spsppsSize = 0;

    payload.spsppsBuffer = spsppsData;
    payload.inBufferSize = sizeof(spsppsData);
    payload.outSPSPPSPayloadSize = &spsppsSize;
    MTENC_API_CALL(m_nvenc.mtEncGetSequenceParams(m_hEncoder, &payload));
    seqParams.clear();
    seqParams.insert(seqParams.end(), &spsppsData[0], &spsppsData[spsppsSize]);
}

MTENCSTATUS MtEncoder::DoEncode(MT_ENC_INPUT_PTR inputBuffer, MT_ENC_OUTPUT_PTR outputBuffer, MT_ENC_PIC_PARAMS *pPicParams)
{
    NVTX_SCOPED_RANGE("DoEncode")
    MT_ENC_PIC_PARAMS picParams = {};
    if (pPicParams)
    {
        picParams = *pPicParams;
    }

    HEVC_3D_REFERENCE_DISPLAY_INFO *p3dReferenceDisplayInfo = NULL;
    picParams.version = MT_ENC_PIC_PARAMS_VER;
    picParams.pictureStruct = MT_ENC_PIC_STRUCT_FRAME;
    picParams.inputTimeStamp = m_nInputTimeStamp++;
    picParams.inputBuffer = inputBuffer;
    picParams.bufferFmt = GetPixelFormat();
    picParams.inputWidth = GetEncodeWidth();
    picParams.inputHeight = GetEncodeHeight();
    picParams.frameIdx = m_iToSend;
    picParams.outputBitstream = outputBuffer;
    picParams.completionEvent = GetCompletionEvent(m_iToSend % m_nEncoderBuffer);

    if (m_enableStereoMVHEVC)
    {
        picParams.codecPicParams.hevcPicParams.viewId = m_viewId;
        m_viewId = m_viewId ^ 1;
        if (m_outputHevc3DReferenceDisplayInfo == 1)
        {

            // Example code to insert HEVC_3D_REFERENCE_DISPLAY_INFO
            // One 3D Reference Displays Information SEI message NAL unit (per G.14.2.3), with
            // nuh_layer_id equal to 0, and with the following values:
            // - To indicate the display width value is unspecified by using 0, use:
            //   - prec_ref_display_width = 31
            //   - exponent_ref_display_width = 0
            //   - mantissa_ref_display_width = 0
            // - ref_viewing_distance_flag = 0
            // - prec_ref_viewing_dist syntax element skipped
            // - num_ref_displays_minusl = 0
            // - left_view_id[ 0 ] is set to reference the texture layer used for the viewer_s left
            //   eye using values in vps_extension (per F.7.3.2.1.1)
            // - right_view_id[ 0 ] is set to reference the texture layer used for the viewer_s
            //   right eye using values in vps_extension (per F.7.3.2.1.1)
            // - additional_shift_present_flag[ 0 ] = 0
            // - exponent_ref_viewing_distancel 0 ], mantissa_ref_viewing_distance[ 0 ],
            //   num_sample_shift_plus512[ 0 ] syntax elements are skipped
            p3dReferenceDisplayInfo = new HEVC_3D_REFERENCE_DISPLAY_INFO;
            memset(p3dReferenceDisplayInfo, 0, sizeof(HEVC_3D_REFERENCE_DISPLAY_INFO));
            p3dReferenceDisplayInfo->precRefDisplayWidth = 31;
            p3dReferenceDisplayInfo->leftViewId[0] = 0;
            p3dReferenceDisplayInfo->rightViewId[0] = 1;
            picParams.codecPicParams.hevcPicParams.p3DReferenceDisplayInfo = p3dReferenceDisplayInfo;
        }
    }

    MTENCSTATUS nvStatus = m_nvenc.mtEncEncodePicture(m_hEncoder, &picParams);

    if (p3dReferenceDisplayInfo)
    {
        delete p3dReferenceDisplayInfo;
        p3dReferenceDisplayInfo = NULL;
    }

    return nvStatus; 
}

void MtEncoder::SendEOS()
{
    MT_ENC_PIC_PARAMS picParams = { MT_ENC_PIC_PARAMS_VER };
    picParams.encodePicFlags = MT_ENC_PIC_FLAG_EOS;
    picParams.completionEvent = GetCompletionEvent(m_iToSend % m_nEncoderBuffer);
    MTENC_API_CALL(m_nvenc.mtEncEncodePicture(m_hEncoder, &picParams));
}

void MtEncoder::EndEncode(std::vector<NvEncOutputFrame> &vPacket)
{
    vPacket.clear();
    if (!IsHWEncoderInitialized())
    {
        PYNVVC_THROW_ERROR("Encoder device not initialized", MT_ENC_ERR_ENCODER_NOT_INITIALIZED);
    }

    SendEOS();

    GetEncodedPacket(m_vBitstreamOutputBuffer, vPacket, false);
}

void MtEncoder::GetEncodedPacket(std::vector<MT_ENC_OUTPUT_PTR> &vOutputBuffer, std::vector<NvEncOutputFrame> &vPacket, bool bOutputDelay)
{
    unsigned i = 0;
    int iEnd = bOutputDelay ? m_iToSend - m_nOutputDelay : m_iToSend;
    for (; m_iGot < iEnd; m_iGot++)
    {
        WaitForCompletionEvent(m_iGot % m_nEncoderBuffer);
        MT_ENC_LOCK_BITSTREAM lockBitstreamData = { MT_ENC_LOCK_BITSTREAM_VER };
        lockBitstreamData.outputBitstream = vOutputBuffer[m_iGot % m_nEncoderBuffer];
        lockBitstreamData.doNotWait = false;
        MTENC_API_CALL(m_nvenc.mtEncLockBitstream(m_hEncoder, &lockBitstreamData));
  
        uint8_t *pData = (uint8_t *)lockBitstreamData.bitstreamBufferPtr;
        if (vPacket.size() < i + 1)
        {
            NvEncOutputFrame nvEncOutputFrame;
            vPacket.push_back(nvEncOutputFrame);
        }
        vPacket[i].frame.clear();
       
        if ((m_initializeParams.encodeGUID == MT_ENC_CODEC_AV1_GUID) && (m_bUseIVFContainer))
        {
            if (m_bWriteIVFFileHeader)
            {
                m_IVFUtils.WriteFileHeader(vPacket[i].frame, MAKE_FOURCC('A', 'V', '0', '1'), m_initializeParams.encodeWidth, m_initializeParams.encodeHeight, m_initializeParams.frameRateNum, m_initializeParams.frameRateDen, 0xFFFF);
                m_bWriteIVFFileHeader = false;
            }

            m_IVFUtils.WriteFrameHeader(vPacket[i].frame, lockBitstreamData.bitstreamSizeInBytes, lockBitstreamData.outputTimeStamp);
        }
        vPacket[i].frame.insert(vPacket[i].frame.end(), &pData[0], &pData[lockBitstreamData.bitstreamSizeInBytes]);
        vPacket[i].pictureType = lockBitstreamData.pictureType;
        vPacket[i].timeStamp = lockBitstreamData.outputTimeStamp;
        i++;

        MTENC_API_CALL(m_nvenc.mtEncUnlockBitstream(m_hEncoder, lockBitstreamData.outputBitstream));

        if (m_vMappedInputBuffers[m_iGot % m_nEncoderBuffer])
        {
            MTENC_API_CALL(m_nvenc.mtEncUnmapInputResource(m_hEncoder, m_vMappedInputBuffers[m_iGot % m_nEncoderBuffer]));
            m_vMappedInputBuffers[m_iGot % m_nEncoderBuffer] = nullptr;
        }

        if (m_bMotionEstimationOnly && m_vMappedRefBuffers[m_iGot % m_nEncoderBuffer])
        {
            MTENC_API_CALL(m_nvenc.mtEncUnmapInputResource(m_hEncoder, m_vMappedRefBuffers[m_iGot % m_nEncoderBuffer]));
            m_vMappedRefBuffers[m_iGot % m_nEncoderBuffer] = nullptr;
        }
    }
}

bool MtEncoder::Reconfigure(const MT_ENC_RECONFIGURE_PARAMS *pReconfigureParams)
{
    MTENCSTATUS reconfigStatus = m_nvenc.mtEncReconfigureEncoder(m_hEncoder, const_cast<MT_ENC_RECONFIGURE_PARAMS*>(pReconfigureParams));
    // Same UNSUPPORTED_PARAM fallback as in Initialize: some MTENC driver
    // versions reject two-pass rc params on reconfigure; retry once disabled.
    if (reconfigStatus == MT_ENC_ERR_UNSUPPORTED_PARAM &&
        pReconfigureParams->reInitEncodeParams.encodeConfig &&
        pReconfigureParams->reInitEncodeParams.encodeConfig->rcParams.multiPass != MT_ENC_MULTI_PASS_DISABLED)
    {
        LOG(WARNING) << "mtEncReconfigureEncoder rejected two-pass encoding; "
                        "retrying with multipass disabled\n";
        MT_ENC_RECONFIGURE_PARAMS fallback = *pReconfigureParams;
        MT_ENC_CONFIG fallbackConfig = *pReconfigureParams->reInitEncodeParams.encodeConfig;
        fallbackConfig.rcParams.multiPass = MT_ENC_MULTI_PASS_DISABLED;
        fallback.reInitEncodeParams.encodeConfig = &fallbackConfig;
        reconfigStatus = m_nvenc.mtEncReconfigureEncoder(m_hEncoder, &fallback);
        if (reconfigStatus == MT_ENC_SUCCESS)
        {
            // persist the accepted config below
            memcpy(const_cast<MT_ENC_RECONFIGURE_PARAMS*>(pReconfigureParams)->reInitEncodeParams.encodeConfig,
                   &fallbackConfig, sizeof(fallbackConfig));
        }
    }
    MTENC_API_CALL(reconfigStatus);

    memcpy(&m_initializeParams, &(pReconfigureParams->reInitEncodeParams), sizeof(m_initializeParams));
    if (pReconfigureParams->reInitEncodeParams.encodeConfig)
    {
        memcpy(&m_encodeConfig, pReconfigureParams->reInitEncodeParams.encodeConfig, sizeof(m_encodeConfig));
    }

    m_nWidth = m_initializeParams.encodeWidth;
    m_nHeight = m_initializeParams.encodeHeight;
    m_nMaxEncodeWidth = m_initializeParams.maxEncodeWidth;
    m_nMaxEncodeHeight = m_initializeParams.maxEncodeHeight;

    return true;
}

MT_ENC_REGISTERED_PTR MtEncoder::RegisterResource(void *pBuffer, MT_ENC_INPUT_RESOURCE_TYPE eResourceType,
    int width, int height, int pitch, MT_ENC_BUFFER_FORMAT bufferFormat, MT_ENC_BUFFER_USAGE bufferUsage, 
    MT_ENC_FENCE_POINT_D3D12* pInputFencePoint)
{
    MT_ENC_REGISTER_RESOURCE registerResource = { MT_ENC_REGISTER_RESOURCE_VER };
    registerResource.resourceType = eResourceType;
    registerResource.resourceToRegister = pBuffer;
    registerResource.width = width;
    registerResource.height = height;
    registerResource.pitch = pitch;
    registerResource.bufferFormat = bufferFormat;
    registerResource.bufferUsage = bufferUsage;
    registerResource.pInputFencePoint = pInputFencePoint;
    MTENC_API_CALL(m_nvenc.mtEncRegisterResource(m_hEncoder, &registerResource));

    return registerResource.registeredResource;
}

void MtEncoder::RegisterInputResources(std::vector<void*> inputframes, MT_ENC_INPUT_RESOURCE_TYPE eResourceType,
                                         int width, int height, int pitch, MT_ENC_BUFFER_FORMAT bufferFormat, bool bReferenceFrame)
{
    for (uint32_t i = 0; i < inputframes.size(); ++i)
    {
        MT_ENC_REGISTERED_PTR registeredPtr = RegisterResource(inputframes[i], eResourceType, width, height, pitch, bufferFormat, MT_ENC_INPUT_IMAGE);

        std::vector<uint32_t> _chromaOffsets;
        MtEncoder::GetChromaSubPlaneOffsets(bufferFormat, pitch, height, _chromaOffsets);
        NvEncInputFrame inputframe = {};
        inputframe.inputPtr = (void *)inputframes[i];
        inputframe.chromaOffsets[0] = 0;
        inputframe.chromaOffsets[1] = 0;
        for (uint32_t ch = 0; ch < _chromaOffsets.size(); ch++)
        {
            inputframe.chromaOffsets[ch] = _chromaOffsets[ch];
        }
        inputframe.numChromaPlanes = MtEncoder::GetNumChromaPlanes(bufferFormat);
        inputframe.pitch = pitch;
        inputframe.chromaPitch = MtEncoder::GetChromaPitch(bufferFormat, pitch);
        inputframe.bufferFormat = bufferFormat;
        inputframe.resourceType = eResourceType;

        if (bReferenceFrame)
        {
            m_vRegisteredResourcesForReference.push_back(registeredPtr);
            m_vReferenceFrames.push_back(inputframe);
        }
        else
        {
            m_vRegisteredResources.push_back(registeredPtr);
            m_vInputFrames.push_back(inputframe);
        }
    }
}

void MtEncoder::FlushEncoder()
{
    if (!m_bMotionEstimationOnly && !m_bOutputInVideoMemory)
    {
        // Incase of error it is possible for buffers still mapped to encoder.
        // flush the encoder queue and then unmapped it if any surface is still mapped
        try
        {
            std::vector<NvEncOutputFrame> vPacket;
            EndEncode(vPacket);
        }
        catch (...)
        {

        }
    }
}

void MtEncoder::UnregisterInputResource(MT_ENC_REGISTERED_PTR ptrRegRes)
{
    m_nvenc.mtEncUnregisterResource(m_hEncoder, ptrRegRes);
}

void MtEncoder::ResetCounter()
{
    m_nInputTimeStamp = 0;
}

void MtEncoder::UnregisterInputResources()
{
    FlushEncoder();
    
    if (m_bMotionEstimationOnly)
    {
        for (uint32_t i = 0; i < m_vMappedRefBuffers.size(); ++i)
        {
            if (m_vMappedRefBuffers[i])
            {
                m_nvenc.mtEncUnmapInputResource(m_hEncoder, m_vMappedRefBuffers[i]);
            }
        }
    }
    m_vMappedRefBuffers.clear();

    for (uint32_t i = 0; i < m_vMappedInputBuffers.size(); ++i)
    {
        if (m_vMappedInputBuffers[i])
        {
            m_nvenc.mtEncUnmapInputResource(m_hEncoder, m_vMappedInputBuffers[i]);
        }
    }
    m_vMappedInputBuffers.clear();

    for (uint32_t i = 0; i < m_vRegisteredResources.size(); ++i)
    {
        if (m_vRegisteredResources[i])
        {
            m_nvenc.mtEncUnregisterResource(m_hEncoder, m_vRegisteredResources[i]);
        }
    }
    m_vRegisteredResources.clear();


    for (uint32_t i = 0; i < m_vRegisteredResourcesForReference.size(); ++i)
    {
        if (m_vRegisteredResourcesForReference[i])
        {
            m_nvenc.mtEncUnregisterResource(m_hEncoder, m_vRegisteredResourcesForReference[i]);
        }
    }
    m_vRegisteredResourcesForReference.clear();

}


void MtEncoder::WaitForCompletionEvent(int iEvent)
{
#if defined(_WIN32)
    // Check if we are in async mode. If not, don't wait for event;
    MT_ENC_CONFIG sEncodeConfig = { 0 };
    MT_ENC_INITIALIZE_PARAMS sInitializeParams = { 0 };
    sInitializeParams.encodeConfig = &sEncodeConfig;
    GetInitializeParams(&sInitializeParams);

    if (0U == sInitializeParams.enableEncodeAsync)
    {
        return;
    }
#ifdef DEBUG
    WaitForSingleObject(m_vpCompletionEvent[iEvent], INFINITE);
#else
    // wait for 20s which is infinite on terms of gpu time
    if (WaitForSingleObject(m_vpCompletionEvent[iEvent], 20000) == WAIT_FAILED)
    {
        PYNVVC_THROW_ERROR("Failed to encode frame", MT_ENC_ERR_GENERIC);
    }
#endif
#endif
}

uint32_t MtEncoder::GetWidthInBytes(const MT_ENC_BUFFER_FORMAT bufferFormat, const uint32_t width)
{
    switch (bufferFormat) {
    case MT_ENC_BUFFER_FORMAT_NV12:
    case MT_ENC_BUFFER_FORMAT_YV12:
    case MT_ENC_BUFFER_FORMAT_IYUV:
    case MT_ENC_BUFFER_FORMAT_YUV444:
        return width;
    case MT_ENC_BUFFER_FORMAT_YUV420_10BIT:
    case MT_ENC_BUFFER_FORMAT_P210:
    case MT_ENC_BUFFER_FORMAT_YUV444_10BIT:
        return width * 2;
    case MT_ENC_BUFFER_FORMAT_ARGB:
    case MT_ENC_BUFFER_FORMAT_ARGB10:
    case MT_ENC_BUFFER_FORMAT_AYUV:
    case MT_ENC_BUFFER_FORMAT_ABGR:
    case MT_ENC_BUFFER_FORMAT_ABGR10:
        return width * 4;
    default:
        PYNVVC_THROW_ERROR("Invalid Buffer format", MT_ENC_ERR_INVALID_PARAM);
        return 0;
    }
}

uint32_t MtEncoder::GetNumChromaPlanes(const MT_ENC_BUFFER_FORMAT bufferFormat)
{
    switch (bufferFormat) 
    {
    case MT_ENC_BUFFER_FORMAT_NV12:
    case MT_ENC_BUFFER_FORMAT_YUV420_10BIT:
    case MT_ENC_BUFFER_FORMAT_P210:
        return 1;
    case MT_ENC_BUFFER_FORMAT_YV12:
    case MT_ENC_BUFFER_FORMAT_IYUV:
    case MT_ENC_BUFFER_FORMAT_YUV444:
    case MT_ENC_BUFFER_FORMAT_YUV444_10BIT:
        return 2;
    case MT_ENC_BUFFER_FORMAT_ARGB:
    case MT_ENC_BUFFER_FORMAT_ARGB10:
    case MT_ENC_BUFFER_FORMAT_AYUV:
    case MT_ENC_BUFFER_FORMAT_ABGR:
    case MT_ENC_BUFFER_FORMAT_ABGR10:
        return 0;
    default:
        PYNVVC_THROW_ERROR("Invalid Buffer format", MT_ENC_ERR_INVALID_PARAM);
        return -1;
    }
}

uint32_t MtEncoder::GetChromaPitch(const MT_ENC_BUFFER_FORMAT bufferFormat,const uint32_t lumaPitch)
{
    switch (bufferFormat)
    {
    case MT_ENC_BUFFER_FORMAT_NV12:
    case MT_ENC_BUFFER_FORMAT_YUV420_10BIT:
    case MT_ENC_BUFFER_FORMAT_P210:
    case MT_ENC_BUFFER_FORMAT_YUV444:
    case MT_ENC_BUFFER_FORMAT_YUV444_10BIT:
        return lumaPitch;
    case MT_ENC_BUFFER_FORMAT_YV12:
    case MT_ENC_BUFFER_FORMAT_IYUV:
        return (lumaPitch + 1)/2;
    case MT_ENC_BUFFER_FORMAT_ARGB:
    case MT_ENC_BUFFER_FORMAT_ARGB10:
    case MT_ENC_BUFFER_FORMAT_AYUV:
    case MT_ENC_BUFFER_FORMAT_ABGR:
    case MT_ENC_BUFFER_FORMAT_ABGR10:
        return 0;
    default:
        PYNVVC_THROW_ERROR("Invalid Buffer format", MT_ENC_ERR_INVALID_PARAM);
        return -1;
    }
}

void MtEncoder::GetChromaSubPlaneOffsets(const MT_ENC_BUFFER_FORMAT bufferFormat, const uint32_t pitch, const uint32_t height, std::vector<uint32_t>& chromaOffsets)
{
    chromaOffsets.clear();
    switch (bufferFormat)
    {
    case MT_ENC_BUFFER_FORMAT_NV12:
    case MT_ENC_BUFFER_FORMAT_YUV420_10BIT:
    case MT_ENC_BUFFER_FORMAT_P210:
        chromaOffsets.push_back(pitch * height);
        return;
    case MT_ENC_BUFFER_FORMAT_YV12:
    case MT_ENC_BUFFER_FORMAT_IYUV:
        chromaOffsets.push_back(pitch * height);
        chromaOffsets.push_back(chromaOffsets[0] + (MtEncoder::GetChromaPitch(bufferFormat, pitch) * GetChromaHeight(bufferFormat, height)));
        return;
    case MT_ENC_BUFFER_FORMAT_YUV444:
    case MT_ENC_BUFFER_FORMAT_YUV444_10BIT:
        chromaOffsets.push_back(pitch * height);
        chromaOffsets.push_back(chromaOffsets[0] + (pitch * height));
        return;
    case MT_ENC_BUFFER_FORMAT_ARGB:
    case MT_ENC_BUFFER_FORMAT_ARGB10:
    case MT_ENC_BUFFER_FORMAT_AYUV:
    case MT_ENC_BUFFER_FORMAT_ABGR:
    case MT_ENC_BUFFER_FORMAT_ABGR10:
        return;
    default:
        PYNVVC_THROW_ERROR("Invalid Buffer format", MT_ENC_ERR_INVALID_PARAM);
        return;
    }
}

uint32_t MtEncoder::GetChromaHeight(const MT_ENC_BUFFER_FORMAT bufferFormat, const uint32_t lumaHeight)
{
    switch (bufferFormat)
    {
    case MT_ENC_BUFFER_FORMAT_YV12:
    case MT_ENC_BUFFER_FORMAT_IYUV:
    case MT_ENC_BUFFER_FORMAT_NV12:
    case MT_ENC_BUFFER_FORMAT_YUV420_10BIT:
        return (lumaHeight + 1)/2;
    case MT_ENC_BUFFER_FORMAT_P210:
        return lumaHeight;
    case MT_ENC_BUFFER_FORMAT_YUV444:
    case MT_ENC_BUFFER_FORMAT_YUV444_10BIT:
        return lumaHeight;
    case MT_ENC_BUFFER_FORMAT_ARGB:
    case MT_ENC_BUFFER_FORMAT_ARGB10:
    case MT_ENC_BUFFER_FORMAT_AYUV:
    case MT_ENC_BUFFER_FORMAT_ABGR:
    case MT_ENC_BUFFER_FORMAT_ABGR10:
        return 0;
    default:
        PYNVVC_THROW_ERROR("Invalid Buffer format", MT_ENC_ERR_INVALID_PARAM);
        return 0;
    }
}

uint32_t MtEncoder::GetChromaWidthInBytes(const MT_ENC_BUFFER_FORMAT bufferFormat, const uint32_t lumaWidth)
{
    switch (bufferFormat)
    {
    case MT_ENC_BUFFER_FORMAT_YV12:
    case MT_ENC_BUFFER_FORMAT_IYUV:
        return (lumaWidth + 1) / 2;
    case MT_ENC_BUFFER_FORMAT_NV12:
        return lumaWidth;
    case MT_ENC_BUFFER_FORMAT_YUV420_10BIT:
        return 2 * lumaWidth;
    case MT_ENC_BUFFER_FORMAT_P210:
        return 2 * lumaWidth;
    case MT_ENC_BUFFER_FORMAT_YUV444:
        return lumaWidth;
    case MT_ENC_BUFFER_FORMAT_YUV444_10BIT:
        return 2 * lumaWidth;
    case MT_ENC_BUFFER_FORMAT_ARGB:
    case MT_ENC_BUFFER_FORMAT_ARGB10:
    case MT_ENC_BUFFER_FORMAT_AYUV:
    case MT_ENC_BUFFER_FORMAT_ABGR:
    case MT_ENC_BUFFER_FORMAT_ABGR10:
        return 0;
    default:
        PYNVVC_THROW_ERROR("Invalid Buffer format", MT_ENC_ERR_INVALID_PARAM);
        return 0;
    }
}


int MtEncoder::GetCapabilityValue(GUID guidCodec, MT_ENC_CAPS capsToQuery)
{
    if (!m_hEncoder)
    {
        return 0;
    }
    MT_ENC_CAPS_PARAM capsParam = { MT_ENC_CAPS_PARAM_VER };
    capsParam.capsToQuery = capsToQuery;
    int v;
    m_nvenc.mtEncGetEncodeCaps(m_hEncoder, guidCodec, &capsParam, &v);
    return v;
}

int MtEncoder::GetFrameSize() const
{
    switch (GetPixelFormat())
    {
    case MT_ENC_BUFFER_FORMAT_YV12:
    case MT_ENC_BUFFER_FORMAT_IYUV:
    case MT_ENC_BUFFER_FORMAT_NV12:
        return GetEncodeWidth() * (GetEncodeHeight() + (GetEncodeHeight() + 1) / 2);
    case MT_ENC_BUFFER_FORMAT_YUV420_10BIT:
        return 2 * GetEncodeWidth() * (GetEncodeHeight() + (GetEncodeHeight() + 1) / 2);
    case MT_ENC_BUFFER_FORMAT_P210:
        return 4 * GetEncodeWidth() * GetEncodeHeight();
    case MT_ENC_BUFFER_FORMAT_YUV444:
        return GetEncodeWidth() * GetEncodeHeight() * 3;
    case MT_ENC_BUFFER_FORMAT_YUV444_10BIT:
        return 2 * GetEncodeWidth() * GetEncodeHeight() * 3;
    case MT_ENC_BUFFER_FORMAT_ARGB:
    case MT_ENC_BUFFER_FORMAT_ARGB10:
    case MT_ENC_BUFFER_FORMAT_AYUV:
    case MT_ENC_BUFFER_FORMAT_ABGR:
    case MT_ENC_BUFFER_FORMAT_ABGR10:
        return 4 * GetEncodeWidth() * GetEncodeHeight();
    default:
        PYNVVC_THROW_ERROR("Invalid Buffer format", MT_ENC_ERR_INVALID_PARAM);
        return 0;
    }
}

void MtEncoder::GetInitializeParams(MT_ENC_INITIALIZE_PARAMS *pInitializeParams)
{
    if (!pInitializeParams || !pInitializeParams->encodeConfig)
    {
        PYNVVC_THROW_ERROR("Both pInitializeParams and pInitializeParams->encodeConfig can't be NULL", MT_ENC_ERR_INVALID_PTR);
    }
    MT_ENC_CONFIG *pEncodeConfig = pInitializeParams->encodeConfig;
    *pEncodeConfig = m_encodeConfig;
    *pInitializeParams = m_initializeParams;
    pInitializeParams->encodeConfig = pEncodeConfig;
}

void MtEncoder::InitializeBitstreamBuffer()
{
    for (int i = 0; i < m_nEncoderBuffer; i++)
    {
        MT_ENC_CREATE_BITSTREAM_BUFFER createBitstreamBuffer = { MT_ENC_CREATE_BITSTREAM_BUFFER_VER };
        MTENC_API_CALL(m_nvenc.mtEncCreateBitstreamBuffer(m_hEncoder, &createBitstreamBuffer));
        m_vBitstreamOutputBuffer[i] = createBitstreamBuffer.bitstreamBuffer;
    }
}

void MtEncoder::DestroyBitstreamBuffer()
{
    for (uint32_t i = 0; i < m_vBitstreamOutputBuffer.size(); i++)
    {
        if (m_vBitstreamOutputBuffer[i])
        {
            m_nvenc.mtEncDestroyBitstreamBuffer(m_hEncoder, m_vBitstreamOutputBuffer[i]);
        }
    }

    m_vBitstreamOutputBuffer.clear();
}

void MtEncoder::InitializeMVOutputBuffer()
{
    for (int i = 0; i < m_nEncoderBuffer; i++)
    {
        MT_ENC_CREATE_MV_BUFFER createMVBuffer = { MT_ENC_CREATE_MV_BUFFER_VER };
        MTENC_API_CALL(m_nvenc.mtEncCreateMVBuffer(m_hEncoder, &createMVBuffer));
        m_vMVDataOutputBuffer.push_back(createMVBuffer.mvBuffer);
    }
}

void MtEncoder::DestroyMVOutputBuffer()
{
    for (uint32_t i = 0; i < m_vMVDataOutputBuffer.size(); i++)
    {
        if (m_vMVDataOutputBuffer[i])
        {
            m_nvenc.mtEncDestroyMVBuffer(m_hEncoder, m_vMVDataOutputBuffer[i]);
        }
    }

    m_vMVDataOutputBuffer.clear();
}

MTENCSTATUS MtEncoder::DoMotionEstimation(MT_ENC_INPUT_PTR inputBuffer, MT_ENC_INPUT_PTR inputBufferForReference, MT_ENC_OUTPUT_PTR outputBuffer)
{
    MT_ENC_MEONLY_PARAMS meParams = { MT_ENC_MEONLY_PARAMS_VER };
    meParams.inputBuffer = inputBuffer;
    meParams.referenceFrame = inputBufferForReference;
    meParams.inputWidth = GetEncodeWidth();
    meParams.inputHeight = GetEncodeHeight();
    meParams.mvBuffer = outputBuffer;
    meParams.completionEvent = GetCompletionEvent(m_iToSend % m_nEncoderBuffer);
    MTENCSTATUS nvStatus = m_nvenc.mtEncRunMotionEstimationOnly(m_hEncoder, &meParams);
    
    return nvStatus;
}


#endif //MTENC_VER_13_0