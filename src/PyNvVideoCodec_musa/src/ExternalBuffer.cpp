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
#include "NvCodecUtils.h"

#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include <string>
#include <functional> // for std::multiplies

using namespace py::literals;

ExternalBuffer::ExternalBuffer(DLPackTensor &&dlTensor)
{
    if (!IsCudaAccessible(dlTensor->device.device_type))
    {
        throw std::runtime_error("Only MUSA memory buffers can be wrapped");
    }

    if (dlTensor->data != nullptr)
    {
        CheckValidMUSABuffer(dlTensor->data);
    }

    m_dlTensor = std::move(dlTensor);
}

py::tuple ExternalBuffer::shape() const
{
    py::tuple shape(m_dlTensor->ndim);
    for (size_t i = 0; i < shape.size(); ++i)
    {
        shape[i] = m_dlTensor->shape[i];
    }

    return shape;
}

py::tuple ExternalBuffer::strides() const
{
    py::tuple strides(m_dlTensor->ndim);

    for (size_t i = 0; i < strides.size(); ++i)
    {
        strides[i] = m_dlTensor->strides[i];
    }

    return strides;
}

std::string ExternalBuffer::dtype() const
{
    return std::string("|u1");
    //return (m_dlTensor->dtype);

}

void *ExternalBuffer::data() const
{
    return m_dlTensor->data;
}

py::capsule ExternalBuffer::dlpack(py::object consumer_stream, MUstream producer_stream, MUevent producer_stream_event) const
{
    struct ManagerCtx
    {
        DLManagedTensor tensor;
        std::shared_ptr<const ExternalBuffer> extBuffer;
    };

    if (m_dlTensor->device.device_type == kDLExtDev)
    {
        MUstream consumer_custream = nullptr;
        // Caveat: DLPack semantics use int for stream objects. For MUSA's case it is
        // a int64_t value. Need to check how this impacts.
        auto consumer_raw_stream = consumer_stream.cast<int64_t>();
        // 0 implies throw
        // 1 implies legacy default
        // 2 implies PTDS
        // -1 implies no sync
        // reference for semantics:
        // https://data-apis.org/array-api/2022.12/API_specification/generated/array_api.array.__dlpack__.html
        if (consumer_raw_stream == 0)
        {
            std::string msg = "Invalid value for stream parameter. Passed value of 0 which is not allowed\n";
            PYNVVC_THROW_ERROR(msg, MUSA_ERROR_NOT_SUPPORTED);
        }
        else if (consumer_raw_stream == 1)
        {
            consumer_custream = MU_STREAM_LEGACY;
        }
        else if (consumer_raw_stream == 2)
        {
            consumer_custream = MU_STREAM_PER_THREAD;
        }
        else if (consumer_raw_stream != -1)
        {
            consumer_custream = reinterpret_cast<MUstream>(consumer_raw_stream);
        }

        if (consumer_raw_stream != -1)
        {
            if (producer_stream != consumer_custream)
            {
                // Note that producer event is recorded in decoder on a per frame
                // basis and the event is stored in DecodedFrame structure returned
                // to user. The caller of this functions fetches stream from 
                // DecodedFrame and passes to this function.
                ck(muCtxPushCurrent(m_cuContext));
                ck(muStreamWaitEvent(consumer_custream, producer_stream_event, 0));
                ck(muCtxPopCurrent(nullptr));
            }    
        }
    }
    else if (m_dlTensor->device.device_type != kDLCPU)
    {
        LOG(WARNING) << "Unsupported Device Type. Should not reach here\n";
    }

    auto ctx = std::make_unique<ManagerCtx>();

    // Set up tensor deleter to delete the ManagerCtx
    ctx->tensor.manager_ctx = ctx.get();
    ctx->tensor.deleter = [](DLManagedTensor *tensor)
    {
        auto *ctx = static_cast<ManagerCtx *>(tensor->manager_ctx);
        delete ctx;
    };

    // Copy tensor data
    ctx->tensor.dl_tensor = *m_dlTensor;

    // Manager context holds a reference to this External Buffer so that
    // GC doesn't delete this buffer while the dlpack tensor still refers to it.
    ctx->extBuffer = this->shared_from_this();

    // Creates the python capsule with the DLManagedTensor instance we're returning.
    py::capsule cap(&ctx->tensor, "dltensor", [](PyObject *ptr)
                    {
                        if(PyCapsule_IsValid(ptr, "dltensor"))
                        {
                            // If consumer didn't delete the tensor,
                            if(auto *dlTensor = static_cast<DLManagedTensor *>(PyCapsule_GetPointer(ptr, "dltensor")))
                            {
                                // Delete the tensor.
                                if(dlTensor->deleter != nullptr)
                                {
                                    dlTensor->deleter(dlTensor);
                                }
                            }
                        }
                    });

    // Now that the capsule is created and the manager ctx was transfered to it,
    // we can release the unique_ptr.
    ctx.release();

    return cap;
}

py::tuple ExternalBuffer::dlpackDevice() const
{
    return py::make_tuple(py::int_(static_cast<int>(m_dlTensor->device.device_type)),
                          py::int_(static_cast<int>(m_dlTensor->device.device_id)));
}

const DLTensor &ExternalBuffer::dlTensor() const
{
    return *m_dlTensor;
}

int ExternalBuffer::LoadDLPack(std::vector<size_t> _shape, std::vector<size_t> _stride, std::string _typeStr,
                               MUdeviceptr _data, bool useDeviceMemory, uint32_t deviceId, const MUcontext context)
{
    m_dlTensor->byte_offset = 0;
    // musify: DLPack bundled with torch_musa 2.9.1 uses kDLExtDev for PrivateUse1/MUSA tensors.
    m_dlTensor->device.device_type = useDeviceMemory ? kDLExtDev : kDLCPU;
    m_dlTensor->device.device_id = useDeviceMemory ? deviceId : 0;

    void* ptr = reinterpret_cast<void*>(_data);
    if (useDeviceMemory)
    {
        m_cuContext = context;
        ck(muCtxPushCurrent(context));
        CheckValidMUSABuffer(ptr);
        ck(muCtxPopCurrent(nullptr));
    }
    m_dlTensor->data = ptr;

    // Convert DataType
    if (_typeStr != "|u1" && _typeStr != "B" && _typeStr != "|u2")
    {
        throw std::runtime_error("Could not create DL Pack tensor! Invalid typstr: " + _typeStr);
        return -1;
    }

    int itemSizeDT = sizeof(uint8_t);// dt.itemsize() 
    m_dlTensor->dtype.code = kDLUInt;
    m_dlTensor->dtype.bits = 8;
    m_dlTensor->dtype.lanes = 1;

    if (_typeStr == "|u2")
    {
        itemSizeDT = sizeof(uint16_t);
        m_dlTensor->dtype.bits = 16;
    }

    // Convert ndim
    m_dlTensor->ndim = _shape.size();

    delete[] m_dlTensor->shape;
    m_dlTensor->shape = nullptr;

    delete[] m_dlTensor->strides;
    m_dlTensor->strides = nullptr;

    // Convert shape
    auto *shape = new int64_t[m_dlTensor->ndim];
    m_dlTensor->shape = shape;
    for (int i = 0; i < m_dlTensor->ndim; ++i)
    {
        shape[i] = _shape[i];
    }

    // Convert strides
    auto *strides = new int64_t[m_dlTensor->ndim];
    m_dlTensor->strides = strides;
    for (int i = 0; i < m_dlTensor->ndim; ++i)
    {
        strides[i] = _stride[i];
    }

    return 0;
}
