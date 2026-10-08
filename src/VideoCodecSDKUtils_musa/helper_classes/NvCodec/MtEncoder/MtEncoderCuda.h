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

#pragma once

#include <vector>
#include <stdint.h>
#include <mutex>
#include <musa.h>
#include "MtEncoder_130.h"

#ifndef MUSA_DRVAPI_CALL
#define MUSA_DRVAPI_CALL( call )                                                                                                 \
    do                                                                                                                           \
    {                                                                                                                            \
        MUresult err__ = call;                                                                                                   \
        if (err__ != MUSA_SUCCESS)                                                                                               \
        {                                                                                                                        \
            const char *szErrName = NULL;                                                                                        \
            muGetErrorName(err__, &szErrName);                                                                                   \
            std::ostringstream errorLog;                                                                                         \
            errorLog << "MUSA driver API error " << szErrName ;                                                                  \
            throw PyNvVCException<PyNvVCGenericError>::makePyNvVCException(errorLog.str(), MT_ENC_ERR_GENERIC, __FUNCTION__, __FILE__, __LINE__);      \
        }                                                                                                                        \
    }                                                                                                                            \
    while (0)
#endif // !1

/**
*  @brief Encoder for MUSA device memory.
*/
class MtEncoderCuda : public MtEncoder
{
public:
    MtEncoderCuda(MUcontext cuContext,MUstream cuStream,uint32_t nWidth, uint32_t nHeight, MT_ENC_BUFFER_FORMAT eBufferFormat,
        uint32_t nExtraOutputDelay = 3, bool bMotionEstimationOnly = false, bool bOPInVideoMemory = false, 
        bool bUseIVFContainer = true, bool bRepeatSequenceHeader = false);
    virtual ~MtEncoderCuda();

    /**
    *  @brief This is a static function to copy input data from host memory to device memory.
    *  This function assumes YUV plane is a single contiguous memory segment.
    */
    static void CopyToDeviceFrame(MUcontext device,
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
        bool bUnAlignedDeviceCopy = false,
        MUstream stream = NULL,
        const uint32_t srcChromaOffsets[] = NULL);

    /**
    *  @brief This is a static function to copy input data from host memory to device memory.
    *  Application must pass a seperate device pointer for each YUV plane.
    */
    static void CopyToDeviceFrame(MUcontext device,
        void* pSrcFrame,
        uint32_t nSrcPitch,
        MUdeviceptr pDstFrame,
        uint32_t dstPitch,
        int width,
        int height,
        MUmemorytype srcMemoryType,
        MT_ENC_BUFFER_FORMAT pixelFormat,
        MUdeviceptr dstChromaPtr[],
        uint32_t dstChromaPitch,
        uint32_t numChromaPlanes,
        bool bUnAlignedDeviceCopy = false);

    MT_ENCODE_API_FUNCTION_LIST GetApi() const { return m_nvenc;}

    void*                       GetEncoder() const { return m_hEncoder;}
    /**
    *  @brief This function sets input and output MUSA streams
    */
    void SetIOCudaStreams(MT_ENC_MUSTREAM_PTR inputStream, MT_ENC_MUSTREAM_PTR outputStream);

protected:
    /**
    *  @brief This function is used to release the input buffers allocated for encoding.
    *  This function is an override of virtual function MtEncoder::ReleaseInputBuffers().
    */
    virtual void ReleaseInputBuffers() override;

private:
    /**
    *  @brief This function is used to allocate input buffers for encoding.
    *  This function is an override of virtual function MtEncoder::AllocateInputBuffers().
    */
    virtual void AllocateInputBuffers(int32_t numInputBuffers) override;

private:
    /**
    *  @brief This is a private function to release MUSA device memory used for encoding.
    */
    void ReleaseCudaResources();

protected:
    MUcontext m_cuContext;
    MUstream  m_cuStream;

private:
    size_t m_musaPitch = 0;
};
