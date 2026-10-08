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

#pragma once
#ifndef _WIN32
#include "../../Interface/mtmuvid.h"
#else
#include "..\..\Interface\mtmuvid.h"
#endif
#include "muvid_dlopen.h"
#include <stdint.h>

typedef struct CuvidFunctions {
  muvid_lib lib;
  MUresult (*muvidGetDecoderCaps)(MUVIDDECODECAPS* pdc);
  MUresult (*muvidCreateDecoder)(MUvideodecoder* phDecoder,
                                 MUVIDDECODECREATEINFO* pdci);
  MUresult (*muvidDestroyDecoder)(MUvideodecoder hDecoder);
  MUresult (*muvidDecodePicture)(MUvideodecoder hDecoder,
                                 MUVIDPICPARAMS* pPicParams);
  MUresult (*muvidGetDecodeStatus)(MUvideodecoder hDecoder, int nPicIdx,
                                   MUVIDGETDECODESTATUS* pDecodeStatus);
  MUresult (*muvidReconfigureDecoder)(
      MUvideodecoder hDecoder, MUVIDRECONFIGUREDECODERINFO* pDecReconfigParams);
  // MUresult (*muvidMapVideoFrame)(MUvideodecoder hDecoder, int nPicIdx,
  // unsigned int* pDevPtr, unsigned int* pPiMUVIDh,
  // MUVIDPROCPARAMS* pVPP);
  // MUresult (*muvidUnmapVideoFrame)(MUvideodecoder hDecoder,
  // unsigned int DevPtr);
  MUresult (*muvidMapVideoFrame64)(MUvideodecoder hDecoder, int nPicIdx,
                                   MUdeviceptr* pDevPtr, unsigned int* pPiMUVIDh,
                                   MUVIDPROCPARAMS* pVPP);
  MUresult (*muvidUnmapVideoFrame64)(MUvideodecoder hDecoder,
                                     unsigned long long DevPtr);
  MUresult (*muvidCtxLockCreate)(MUvideoctxlock* pLock, MUcontext ctx);
  MUresult (*muvidCtxLockDestroy)(MUvideoctxlock lck);
  MUresult (*muvidCtxLock)(MUvideoctxlock lck, unsigned int reserved_flags);
  MUresult (*muvidCtxUnlock)(MUvideoctxlock lck, unsigned int reserved_flags);

  MUresult (*muvidCreateVideoParser)(MUvideoparser* pObj,
                                     MUVIDPARSERPARAMS* pParams);
  MUresult (*muvidParseVideoData)(MUvideoparser obj,
                                  MUVIDSOURCEDATAPACKET* pPacket);
  MUresult (*muvidDestroyVideoParser)(MUvideoparser obj);

  MUresult (*muvidCreateVideoSource)(MUvideosource* pObj,
                                     const char* pszFileName,
                                     MUVIDSOURCEPARAMS* pParams);
  MUresult (*muvidCreateVideoSourceW)(MUvideosource* pObj,
                                      const wchar_t* pwszFileName,
                                      MUVIDSOURCEPARAMS* pParams);
  MUresult (*muvidDestroyVideoSource)(MUvideosource obj);
  MUresult (*muvidSetVideoSourceState)(MUvideosource obj, musaVideoState state);
  musaVideoState (*muvidGetVideoSourceState)(MUvideosource obj);
  MUresult (*muvidGetSourceVideoFormat)(MUvideosource obj,
                                        MUVIDEOFORMAT* pvidfmt,
                                        unsigned int flags);
  MUresult (*muvidGetSourceAudioFormat)(MUvideosource obj,
                                        MUAUDIOFORMAT* paudfmt,
                                        unsigned int flags);
} CuvidFunctions;

#define MUVID_LOAD_STRINGIFY(s) _MUVID_LOAD_STRINGIFY(s)
#define _MUVID_LOAD_STRINGIFY(s) #s

#define MUVID_LOAD_LIBRARY(api, symbol)                                        \
  (api).symbol = (decltype((api).symbol))muvid_dlsym(                             \
      (api).lib, MUVID_LOAD_STRINGIFY(symbol));                                \
  if (!(api).symbol) {                                                         \
    err = "Could not load function \"" MUVID_LOAD_STRINGIFY(symbol) "\"";      \
    goto err;                                                                  \
  }
#define MUVID_UNLOAD_LIBRARY(api, symbol) (api).symbol = NULL;

static const char* unloadCuvidSymbols(CuvidFunctions* muvidApi)
{
  const char* err = NULL;
  if (!muvidApi) {
    return NULL;
  }

  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidGetDecoderCaps);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidCreateDecoder);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidDestroyDecoder);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidDecodePicture);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidGetDecodeStatus);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidReconfigureDecoder);
  // MUVID_UNLOAD_LIBRARY(*muvidApi, muvidMapVideoFrame);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidMapVideoFrame64);
  // MUVID_UNLOAD_LIBRARY(*muvidApi, muvidUnmapVideoFrame);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidUnmapVideoFrame64);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidCtxLockCreate);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidCtxLockDestroy);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidCtxLock);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidCtxUnlock);

  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidCreateVideoParser);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidParseVideoData);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidDestroyVideoParser);

  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidCreateVideoSource);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidCreateVideoSourceW);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidDestroyVideoSource);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidSetVideoSourceState);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidGetVideoSourceState);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidGetSourceVideoFormat);
  MUVID_UNLOAD_LIBRARY(*muvidApi, muvidGetSourceAudioFormat);

  if (muvid_dlclose(muvidApi->lib) != 0) {
    return "Failed to close library handle";
  };
  muvidApi->lib = 0;
  return NULL;
}

static const char* loadCuvidSymbols(CuvidFunctions* muvidApi, const char* path)
{
  const char* err = NULL;
  muvidApi->lib = muvid_dlopen(path);
  if (!muvidApi->lib) {
    return "Failed to open dynamic library: muvid";
  }
  MUVID_LOAD_LIBRARY(*muvidApi, muvidGetDecoderCaps);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidCreateDecoder);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidDestroyDecoder);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidDecodePicture);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidGetDecodeStatus);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidReconfigureDecoder);
  // MUVID_LOAD_LIBRARY(*muvidApi, muvidMapVideoFrame);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidMapVideoFrame64);
  // MUVID_LOAD_LIBRARY(*muvidApi, muvidUnmapVideoFrame);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidUnmapVideoFrame64);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidCtxLockCreate);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidCtxLockDestroy);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidCtxLock);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidCtxUnlock);

  MUVID_LOAD_LIBRARY(*muvidApi, muvidCreateVideoParser);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidParseVideoData);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidDestroyVideoParser);

  MUVID_LOAD_LIBRARY(*muvidApi, muvidCreateVideoSource);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidCreateVideoSourceW);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidDestroyVideoSource);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidSetVideoSourceState);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidGetVideoSourceState);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidGetSourceVideoFormat);
  MUVID_LOAD_LIBRARY(*muvidApi, muvidGetSourceAudioFormat);
  return NULL;

err:
  unloadCuvidSymbols(muvidApi);
  return err;
}
