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

#include "MtEncoderCuda.h"
#include "PyCAIMemoryView.hpp"
#include <map>

namespace py = pybind11;

// This class allocates CUStream.
// It also sets the input and output MUSA stream in the driver, which will be used for pipelining
// pre and post processing MUSA tasks
class NvCUStream
{
private:
    bool mApplicationCreatedStream = false;
public:
    NvCUStream(MUcontext muDevice, MUstream cuStream, std::unique_ptr<MtEncoderCuda>& pEnc)
    {
        device = muDevice;
        MUSA_DRVAPI_CALL(muCtxPushCurrent(device));

        if (cuStream == 0)
        {
            ck(muStreamCreate(&inputStream, MU_STREAM_DEFAULT));
            mApplicationCreatedStream = false;
        }
        else
        {
            inputStream = cuStream;
            mApplicationCreatedStream = true;
        }

        outputStream = inputStream;

        MUSA_DRVAPI_CALL(muCtxPopCurrent(NULL));

        // Set input and output MUSA streams in driver
        pEnc->SetIOCudaStreams((MT_ENC_MUSTREAM_PTR)&inputStream, (MT_ENC_MUSTREAM_PTR)&outputStream);
    }

    ~NvCUStream()
    {
        ck(muCtxPushCurrent(device));

        if (inputStream == outputStream)
        {
            if (inputStream != NULL && !mApplicationCreatedStream)
                ck(muStreamDestroy(inputStream));
        }
        else
        {
            if (inputStream != NULL && !mApplicationCreatedStream)
                ck(muStreamDestroy(inputStream));

            if (outputStream != NULL && !mApplicationCreatedStream)
                ck(muStreamDestroy(outputStream));
        }

        ck(muCtxPopCurrent(NULL));
    }

    MUstream GetOutputCUStream() { return outputStream; };
    MUstream GetInputCUStream() { return inputStream; };

private:
    MUcontext device;
    MUstream inputStream = NULL, outputStream = NULL;
};


struct structEncodeReconfigureParams
{
    MT_ENC_PARAMS_RC_MODE  rateControlMode;
    MT_ENC_MULTI_PASS multiPass;
    uint32_t averageBitrate;
    uint32_t vbvBufferSize ;
    uint32_t maxBitRate;
    uint32_t vbvInitialDelay;
    uint32_t frameRateNum;
    uint32_t frameRateDen;
};

class PyMtEncoder {
private:
    MUcontext m_MUcontext = nullptr;
    MUstream m_MUstream = nullptr;
    bool m_ReleasePrimaryContext = false;
    std::map<MUdeviceptr, MT_ENC_REGISTERED_PTR> m_mapPtr;
    size_t m_width;
    size_t m_height;
    uint64_t m_frameNum;
    MT_ENC_BUFFER_FORMAT m_eBufferFormat;
    bool m_bUseCPUInutBuffer;
    GUID m_encodeGUID;
    int m_gpuId = 0;

    const NvEncInputFrame* GetEncoderInput(py::object _frame);
    const NvEncInputFrame* GetEncoderInputFromCPUBuffer(py::array_t<uint8_t, py::array::c_style | py::array::forcecast> _frame);
    std::unique_ptr<NvCUStream> pCUStream;
    structEncodeReconfigureParams m_EncReconfigureParams;
protected:
    std::unique_ptr<MtEncoderCuda> m_encoder;

public:
    explicit PyMtEncoder(int width, int height,  std::string format,
            size_t musastream, size_t musacontext, bool bUseCPUInutBuffer,std::map<std::string, std::string> config);
    PyMtEncoder(PyMtEncoder&& pyenvc);
    PyMtEncoder(PyMtEncoder& pyenvc);
    MT_ENC_REGISTERED_PTR RegisterInputFrame(const py::object obj, const CAIMemoryView frame); 
    bool Reconfigure(structEncodeReconfigureParams reconfigureParams);
    py::bytes Encode(py::object frame, uint8_t picFlags, SEI_MESSAGE sei);
    py::bytes Encode(const py::object frame, uint8_t picFlags);
    py::bytes Encode(py::object _frame);
    py::bytes Encode();
    void UnregisterInputFrame(const CAIMemoryView frame);
    void InitEncodeReconfigureParams(const MT_ENC_INITIALIZE_PARAMS params);
    structEncodeReconfigureParams GetEncodeReconfigureParams();

     ~PyMtEncoder();
};

