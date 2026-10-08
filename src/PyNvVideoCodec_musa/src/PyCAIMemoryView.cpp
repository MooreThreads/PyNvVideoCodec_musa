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

#include <pybind11/stl.h>
#include <pybind11/pybind11.h>
#include "PyCAIMemoryView.hpp"

namespace py = pybind11;

CAIMemoryView  coerceToMusaArrayView(py::object musa_array, MT_ENC_BUFFER_FORMAT bufferFormat, size_t width, size_t height, int planeIdx)
{
  namespace py = pybind11;
  if (!py::hasattr(musa_array, "__musa_array_interface__"))
  {
    throw std::runtime_error("Could not encode MUSA array! Array has no attribute __musa_array_interface__");
  }
  auto array_interface = musa_array.attr("__musa_array_interface__").cast<py::dict>();

  auto [data, readyOnly] = array_interface["data"].cast<std::tuple<MUdeviceptr, bool>>();
  auto shape             = array_interface["shape"].cast<std::vector<size_t>>();
  auto typestr           = array_interface["typestr"].cast<std::string>();
  auto stream            = py::hasattr(array_interface, "stream") ? (MUstream)array_interface["stream"].cast<uint64_t>() : (MUstream)2;

  MUdeviceptr ptr;
  muPointerGetAttribute(&ptr, MU_POINTER_ATTRIBUTE_DEVICE_POINTER, data);
  int gpuIdx;
  ThrowOnCudaError(muPointerGetAttribute(&gpuIdx, MU_POINTER_ATTRIBUTE_DEVICE_ORDINAL, data));

  std::vector<size_t> stride;

  if (stream == (MUstream)0)
  {
    throw std::runtime_error("__musa_array_interface__ protocol specifies that stream must not be 0");
  }
  if (stream == (MUstream)1 || stream == (MUstream)2)
  {
    stream = nullptr;
  }

  std::vector<size_t> expectedShape;
  std::vector<size_t> expectedStrides;

  switch (bufferFormat)
  {
    case MT_ENC_BUFFER_FORMAT_NV12:
      {
        if (typestr != "|u1" && typestr != "B") 
        {
          throw std::runtime_error("Could not encode MUSA array! Invalid typstr: " + typestr);
        }
        expectedShape   = planeIdx == 0 ? std::vector<size_t>{ height, width, 1 } : std::vector<size_t>{ height / 2, width / 2, 2 };
        expectedStrides = planeIdx == 0 ? std::vector<size_t>{ width, 1, 1 } : std::vector<size_t>{ width / 2 * 2, 2, 1 };
        break;
      }
    case MT_ENC_BUFFER_FORMAT_IYUV:
      {
        if (typestr != "|u1" && typestr != "B")
        {
          throw std::runtime_error("Could not encode MUSA array! Invalid typstr: " + typestr);
        }
        if (planeIdx == 0) {
          // Y plane
          expectedShape = std::vector<size_t>{ height, width, 1 };
          expectedStrides = std::vector<size_t>{ width, 1, 1 };
        } else if (planeIdx == 1 || planeIdx == 2) {
          // U or V plane
          expectedShape = std::vector<size_t>{ height / 2, width / 2, 1 };
          expectedStrides = std::vector<size_t>{ width / 2, 1, 1 };
        }
        break;
      }
    case MT_ENC_BUFFER_FORMAT_YUV444:
      {
        if (typestr != "|u1" && typestr != "B")
        {
          throw std::runtime_error("Could not encode MUSA array! Invalid typstr: " + typestr);
        }
        expectedShape = std::vector<size_t>{height, width, 1};
        expectedStrides = std::vector<size_t>{width, 1, 1} ;
        break;
      }
    case MT_ENC_BUFFER_FORMAT_YUV444_10BIT:
      {
        if (typestr != "|u2" && typestr != "B")
        {
          throw std::runtime_error("Could not encode MUSA array! Invalid typstr: " + typestr);
        }
        expectedShape = std::vector<size_t>{height, width, 1};
        expectedStrides = std::vector<size_t>{width*2, 2, 1};
        break;
      }
#if CHECK_API_VERSION(13,0)
    case MT_ENC_BUFFER_FORMAT_P210:
    {
        if (typestr != "|u2" && typestr != "B")
        {
            throw std::runtime_error("Could not encode MUSA array! Invalid typstr: " + typestr);
        }
        if (planeIdx == 0)
        {
            expectedShape = std::vector<size_t>{ height, width, 1 };
            expectedStrides = std::vector<size_t>{ width * 2, 2, 1 };
        }
        else if (planeIdx == 1)
        {
            expectedShape = std::vector<size_t>{ height, width , 1 };
            expectedStrides = std::vector<size_t>{ width * 2, 2, 1 };
        }
        else
        {
            throw std::runtime_error("P210 cannot have more than 2 planees");
        }
        break;
    }
#endif
    case MT_ENC_BUFFER_FORMAT_YUV420_10BIT:
      {
          if (typestr != "|u2" && typestr != "B")
          {
              throw std::runtime_error("Could not encode MUSA array! Invalid typestr: " + typestr);
          }
          if(planeIdx == 0)
          {
              expectedShape = std::vector<size_t>{height, width, 1};
              expectedStrides = std::vector<size_t>{width*2, 2, 1} ;
          }
          else if(planeIdx ==1)
          {
              expectedShape = std::vector<size_t>{height/2, width/2, 2};
              expectedStrides= std::vector<size_t>{width*2, 2, 1};
          }
          else
          {
              throw std::runtime_error("YUV420_10BIT cannot have more than 2 planees");
          }
          break;
      }
    case MT_ENC_BUFFER_FORMAT_YV12 :
      {
          if (typestr != "|u1" && typestr != "B")
          {
              throw std::runtime_error("Could not encode MUSA array! Invalid typstr: " + typestr);
          }
          if(planeIdx == 0)
          {
              expectedShape = std::vector<size_t>{height, width, 1};
              expectedStrides = std::vector<size_t>{width, 1, 1} ;
          }
          if(planeIdx ==1 || planeIdx == 2)
          {
              expectedShape = std::vector<size_t>{height/2, width/2, 1};
              expectedStrides= std::vector<size_t>{width/2, 1, 1};
          }
          break;
      }
     case MT_ENC_BUFFER_FORMAT_ARGB10:
      {
          throw std::runtime_error("ARGB10 format not supported in current release. Use YUV444_16BIT or P010");
          if (typestr != "|u1" && typestr != "B")
          {
              throw std::runtime_error("Could not encode MUSA array! Invalid typstr: " + typestr);
          }
          expectedShape = std::vector<size_t>{height, width, 4};
          expectedStrides = std::vector<size_t>{width*8, 8, 2} ;
          break;
      }
    case MT_ENC_BUFFER_FORMAT_ABGR:
    case MT_ENC_BUFFER_FORMAT_ARGB:
      {
        if (typestr != "|u1" && typestr != "B")
        {
          throw std::runtime_error("Could not encode MUSA array! Invalid typstr: " + typestr);
        }

        expectedShape   = std::vector<size_t>{ height, width, 4 };
        expectedStrides = std::vector<size_t>{ width * 4, 4, 1 };
        break;
      }
    default:
      throw std::runtime_error(std::string("Could not encode MUSA array! Unsupported color format: ") + py::str(py::cast(bufferFormat)).cast<std::string>());
  }
  if (shape != expectedShape)
  {
    std::stringstream ss;
    ss << "Invalid shape: ";
    ss << py::str(py::cast(shape));
    ss << ", expected: ";
    ss << py::str(py::cast(expectedShape));
    throw std::runtime_error(ss.str());
  }
  if (!array_interface["strides"].is_none())
  {
    auto strides = array_interface["strides"].cast<std::vector<size_t>>();
    if (strides != expectedStrides)
    {
      std::stringstream ss;
      ss << "Invalid strides: ";
      ss << py::str(py::cast(strides));
      ss << ", expected: ";
      ss << py::str(py::cast(expectedStrides));
      throw std::runtime_error(ss.str());
    }
  }
  stride = expectedStrides;
  return CAIMemoryView{  shape, stride, typestr,0,data, readyOnly  };
}
