/*
 * This copyright notice applies to this file only
 *
 * SPDX-FileCopyrightText: Copyright (c) 2010-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

#include "MtEncoder/MtEncoderCuda.h"


MtEncoderCuda::MtEncoderCuda(MUcontext cuContext, MUstream cuStream, uint32_t nWidth, uint32_t nHeight, MT_ENC_BUFFER_FORMAT eBufferFormat,
    uint32_t nExtraOutputDelay, bool bMotionEstimationOnly, bool bOutputInVideoMemory, bool bUseIVFContainer, bool bRepeatSequenceHeader):
    MtEncoder(MT_ENC_DEVICE_TYPE_MUSA, cuContext, nWidth, nHeight, eBufferFormat, nExtraOutputDelay, bMotionEstimationOnly, bOutputInVideoMemory, false,
                bUseIVFContainer, bRepeatSequenceHeader), m_cuContext(cuContext), m_cuStream(cuStream)
{
    if (!m_hEncoder) 
    {
        PYNVVC_THROW_ERROR("Encoder Initialization failed", MT_ENC_ERR_INVALID_DEVICE);
    }

    if (!m_cuContext)
    {
        PYNVVC_THROW_ERROR("Invalid Cuda Context", MT_ENC_ERR_INVALID_DEVICE);
    }
}

MtEncoderCuda::~MtEncoderCuda()
{
    ReleaseCudaResources();
}

void MtEncoderCuda::AllocateInputBuffers(int32_t numInputBuffers)
{
    if (!IsHWEncoderInitialized())
    {
        PYNVVC_THROW_ERROR("Encoder intialization failed", MT_ENC_ERR_ENCODER_NOT_INITIALIZED);
    }

    // for MEOnly mode we need to allocate seperate set of buffers for reference frame
    int numCount = m_bMotionEstimationOnly ? 2 : 1;

    for (int count = 0; count < numCount; count++)
    {
        MUSA_DRVAPI_CALL(muCtxPushCurrent(m_cuContext));
        std::vector<void*> inputFrames;
        for (int i = 0; i < numInputBuffers; i++)
        {
            MUdeviceptr pDeviceFrame;
            uint32_t chromaHeight = GetNumChromaPlanes(GetPixelFormat()) * GetChromaHeight(GetPixelFormat(), GetMaxEncodeHeight());
            if (GetPixelFormat() == MT_ENC_BUFFER_FORMAT_YV12 || GetPixelFormat() == MT_ENC_BUFFER_FORMAT_IYUV)
                chromaHeight = GetChromaHeight(GetPixelFormat(), GetMaxEncodeHeight());
            MUSA_DRVAPI_CALL(muMemAllocPitch((MUdeviceptr *)&pDeviceFrame,
                &m_musaPitch,
                GetWidthInBytes(GetPixelFormat(), GetMaxEncodeWidth()),
                GetMaxEncodeHeight() + chromaHeight, 16));
            inputFrames.push_back((void*)pDeviceFrame);
        }
        MUSA_DRVAPI_CALL(muCtxPopCurrent(NULL));

        RegisterInputResources(inputFrames,
            MT_ENC_INPUT_RESOURCE_TYPE_MUSADEVICEPTR,
            GetMaxEncodeWidth(),
            GetMaxEncodeHeight(),
            (int)m_musaPitch,
            GetPixelFormat(),
            (count == 1) ? true : false);
    }
}

void MtEncoderCuda::SetIOCudaStreams(MT_ENC_MUSTREAM_PTR inputStream, MT_ENC_MUSTREAM_PTR outputStream)
{
    MTENC_API_CALL(m_nvenc.mtEncSetIOMusaStreams(m_hEncoder, inputStream, outputStream));
}

void MtEncoderCuda::ReleaseInputBuffers()
{
    ReleaseCudaResources();
}

void MtEncoderCuda::ReleaseCudaResources()
{
    if (!m_hEncoder)
    {
        return;
    }

    if (!m_cuContext)
    {
        return;
    }

    UnregisterInputResources();

    muCtxPushCurrent(m_cuContext);

    for (uint32_t i = 0; i < m_vInputFrames.size(); ++i)
    {
        if (m_vInputFrames[i].inputPtr)
        {
            muMemFree(reinterpret_cast<MUdeviceptr>(m_vInputFrames[i].inputPtr));
        }
    }
    m_vInputFrames.clear();

    for (uint32_t i = 0; i < m_vReferenceFrames.size(); ++i)
    {
        if (m_vReferenceFrames[i].inputPtr)
        {
            muMemFree(reinterpret_cast<MUdeviceptr>(m_vReferenceFrames[i].inputPtr));
        }
    }
    m_vReferenceFrames.clear();

    muCtxPopCurrent(NULL);
    m_cuContext = nullptr;
}

void MtEncoderCuda::CopyToDeviceFrame(MUcontext device,
    void* pSrcFrame,
    uint32_t nSrcPitch,
    MUdeviceptr pDstFrame,
    uint32_t dstPitch,
    int width,
    int height,
    MUmemorytype srcMemoryType,
    MT_ENC_BUFFER_FORMAT pixelFormat,
    const uint32_t dstChromaOffsets[],
    uint32_t numChromaPlanes,
    bool bUnAlignedDeviceCopy,
    MUstream stream,
    const uint32_t _srcChromaOffsets[])
{
    if (srcMemoryType != MU_MEMORYTYPE_HOST && srcMemoryType != MU_MEMORYTYPE_DEVICE)
    {
        PYNVVC_THROW_ERROR("Invalid source memory type for copy", MT_ENC_ERR_INVALID_PARAM);
    }

    NVTX_SCOPED_RANGE("CopyToDeviceFrame_aligned")

    MUSA_DRVAPI_CALL(muCtxPushCurrent(device));

    uint32_t srcPitch = nSrcPitch ? nSrcPitch : MtEncoder::GetWidthInBytes(pixelFormat, width);
    MUSA_MEMCPY2D m = { 0 };
    m.srcMemoryType = srcMemoryType;
    if (srcMemoryType == MU_MEMORYTYPE_HOST)
    {
        m.srcHost = pSrcFrame;
    }
    else
    {
        m.srcDevice = (MUdeviceptr)pSrcFrame;
    }
    m.srcPitch = srcPitch;
    m.dstMemoryType = MU_MEMORYTYPE_DEVICE;
    m.dstDevice = pDstFrame;
    m.dstPitch = dstPitch;
    m.WidthInBytes = MtEncoder::GetWidthInBytes(pixelFormat, width);
    m.Height = height;
    if (bUnAlignedDeviceCopy && srcMemoryType == MU_MEMORYTYPE_DEVICE)
    {
        MUSA_DRVAPI_CALL(muMemcpy2DUnaligned(&m));
    }
    else
    {
        MUSA_DRVAPI_CALL(stream == NULL? muMemcpy2D(&m) : muMemcpy2DAsync(&m, stream));
    }

    std::vector<uint32_t> srcChromaOffsets;
    MtEncoder::GetChromaSubPlaneOffsets(pixelFormat, srcPitch, height, srcChromaOffsets);
    uint32_t chromaHeight = MtEncoder::GetChromaHeight(pixelFormat, height);
    uint32_t destChromaPitch = MtEncoder::GetChromaPitch(pixelFormat, dstPitch);
    uint32_t srcChromaPitch = MtEncoder::GetChromaPitch(pixelFormat, srcPitch);
    uint32_t chromaWidthInBytes = MtEncoder::GetChromaWidthInBytes(pixelFormat, width);

    for (uint32_t i = 0; i < numChromaPlanes; ++i)
    {
        if (chromaHeight)
        {
            if (srcMemoryType == MU_MEMORYTYPE_HOST)
            {
                m.srcHost = ((uint8_t *)pSrcFrame + srcChromaOffsets[i]);
            }
            else
            {
                m.srcDevice = (MUdeviceptr)((uint8_t *)pSrcFrame + srcChromaOffsets[i]);
            }
            m.srcPitch = srcChromaPitch;

            m.dstDevice = (MUdeviceptr)((uint8_t *)pDstFrame + dstChromaOffsets[i]);
            m.dstPitch = destChromaPitch;
            m.WidthInBytes = chromaWidthInBytes;
            m.Height = chromaHeight;
            if (bUnAlignedDeviceCopy && srcMemoryType == MU_MEMORYTYPE_DEVICE)
            {
                MUSA_DRVAPI_CALL(muMemcpy2DUnaligned(&m));
            }
            else
            {
                MUSA_DRVAPI_CALL(stream == NULL? muMemcpy2D(&m) : muMemcpy2DAsync(&m, stream));
            }
        }
    }
    MUSA_DRVAPI_CALL(muCtxPopCurrent(NULL));
}

void MtEncoderCuda::CopyToDeviceFrame(MUcontext device,
    void* pSrcFrame,
    uint32_t nSrcPitch,
    MUdeviceptr pDstFrame,
    uint32_t dstPitch,
    int width,
    int height,
    MUmemorytype srcMemoryType,
    MT_ENC_BUFFER_FORMAT pixelFormat,
    MUdeviceptr dstChromaDevicePtrs[],
    uint32_t dstChromaPitch,
    uint32_t numChromaPlanes,
    bool bUnAlignedDeviceCopy)
{
    if (srcMemoryType != MU_MEMORYTYPE_HOST && srcMemoryType != MU_MEMORYTYPE_DEVICE)
    {
        PYNVVC_THROW_ERROR("Invalid source memory type for copy", MT_ENC_ERR_INVALID_PARAM);
    }

    NVTX_SCOPED_RANGE("CopyToDeviceFrame_unaligned")

    MUSA_DRVAPI_CALL(muCtxPushCurrent(device));

    uint32_t srcPitch = nSrcPitch ? nSrcPitch : MtEncoder::GetWidthInBytes(pixelFormat, width);
    MUSA_MEMCPY2D m = { 0 };
    m.srcMemoryType = srcMemoryType;
    if (srcMemoryType == MU_MEMORYTYPE_HOST)
    {
        m.srcHost = pSrcFrame;
    }
    else
    {
        m.srcDevice = (MUdeviceptr)pSrcFrame;
    }
    m.srcPitch = srcPitch;
    m.dstMemoryType = MU_MEMORYTYPE_DEVICE;
    m.dstDevice = pDstFrame;
    m.dstPitch = dstPitch;
    m.WidthInBytes = MtEncoder::GetWidthInBytes(pixelFormat, width);
    m.Height = height;
    if (bUnAlignedDeviceCopy && srcMemoryType == MU_MEMORYTYPE_DEVICE)
    {
        MUSA_DRVAPI_CALL(muMemcpy2DUnaligned(&m));
    }
    else
    {
        MUSA_DRVAPI_CALL(muMemcpy2D(&m));
    }

    std::vector<uint32_t> srcChromaOffsets;
    MtEncoder::GetChromaSubPlaneOffsets(pixelFormat, srcPitch, height, srcChromaOffsets);
    uint32_t chromaHeight = MtEncoder::GetChromaHeight(pixelFormat, height);
    uint32_t srcChromaPitch = MtEncoder::GetChromaPitch(pixelFormat, srcPitch);
    uint32_t chromaWidthInBytes = MtEncoder::GetChromaWidthInBytes(pixelFormat, width);

    for (uint32_t i = 0; i < numChromaPlanes; ++i)
    {
        if (chromaHeight)
        {
            if (srcMemoryType == MU_MEMORYTYPE_HOST)
            {
                m.srcHost = ((uint8_t *)pSrcFrame + srcChromaOffsets[i]);
            }
            else
            {
                m.srcDevice = (MUdeviceptr)((uint8_t *)pSrcFrame + srcChromaOffsets[i]);
            }
            m.srcPitch = srcChromaPitch;

            m.dstDevice = dstChromaDevicePtrs[i];
            m.dstPitch = dstChromaPitch;
            m.WidthInBytes = chromaWidthInBytes;
            m.Height = chromaHeight;
            if (bUnAlignedDeviceCopy && srcMemoryType == MU_MEMORYTYPE_DEVICE)
            {
                MUSA_DRVAPI_CALL(muMemcpy2DUnaligned(&m));
            }
            else
            {
                MUSA_DRVAPI_CALL(muMemcpy2D(&m));
            }
        }
    }
    MUSA_DRVAPI_CALL(muCtxPopCurrent(NULL));
}
