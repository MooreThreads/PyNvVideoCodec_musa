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


#include "..\..\Interface\mtmuvid.h"
#include <stdint.h>

#ifdef _WIN32
#include <windows.h>
#define muvid_lib HMODULE
#else
#define muvid_lib int
#endif

typedef struct muvidFunctions {
  muvid_lib lib;
  MUresult (*muvidGetDecoderCaps)(muvidDECODECAPS* pdc);
  MUresult (*muvidCreateDecoder)(muvideodecoder* phDecoder,
                                 muvidDECODECREATEINFO* pdci);
  MUresult (*muvidDestroyDecoder)(muvideodecoder hDecoder);
  MUresult (*muvidDecodePicture)(muvideodecoder hDecoder,
                                 muvidPICPARAMS* pPicParams);
  MUresult (*muvidGetDecodeStatus)(muvideodecoder hDecoder, int nPicIdx,
                                   muvidGETDECODESTATUS* pDecodeStatus);
  MUresult (*muvidReconfigureDecoder)(
      muvideodecoder hDecoder, muvidRECONFIGUREDECODERINFO* pDecReconfigParams);
  MUresult (*muvidMapVideoFrame)(muvideodecoder hDecoder, int nPicIdx,
                                 unsigned int* pDevPtr, unsigned int* pPimuvidh,
                                 muvidPROCPARAMS* pVPP);
  MUresult (*muvidUnmapVideoFrame)(muvideodecoder hDecoder,
                                   unsigned int DevPtr);
  MUresult (*muvidMapVideoFrame64)(muvideodecoder hDecoder, int nPicIdx,
                                   unsigned int* pDevPtr, unsigned int* pPimuvidh,
                                   muvidPROCPARAMS* pVPP);
  MUresult (*muvidUnmapVideoFrame64)(muvideodecoder hDecoder,
                                     unsigned long long DevPtr);
  MUresult (*muvidCtxLockCreate)(muvideoctxlock* pLock, MUcontext ctx);
  MUresult (*muvidCtxLockDestroy)(muvideoctxlock lck);
  MUresult (*muvidCtxLock)(muvideoctxlock lck, unsigned int reserved_flags);
  MUresult (*muvidCtxUnlock)(muvideoctxlock lck, unsigned int reserved_flags);
} muvidFunctions;

#define muvid_LOAD_STRINGIFY(s) _muvid_LOAD_STRINGIFY(s)
#define _muvid_LOAD_STRINGIFY(s) #s

#define muvid_LOAD_LIBRARY(api, symbol)                                        \
  (api).(symbol) = muvid_dlsym((api).(lib), (symbol));                            \
  if (!(api).(function)) {                                                     \
    err = "Could not load function \"" muvid_LOAD_STRINGIFY(symbol) "\"";      \
    goto err;                                                                  \
  }
#define muvid_UNLOAD_LIBRARY(api, symbol) (api).(symbol) = NULL;

static const char* unloadmuvidSymbols(muvidFuncitons* muvidApi,
                                      const char* file)
{
  const char* err = NULL;
  if (!muvidApi) {
    return NULL;
  }

  muvid_UNLOAD_LIBRARY(*muvidApi, muvidGetDecoderCaps);
  muvid_UNLOAD_LIBRARY(*muvidApi, muvidCreateDecoder);
  muvid_UNLOAD_LIBRARY(*muvidApi, muvidDestroyDecoder);
  muvid_UNLOAD_LIBRARY(*muvidApi, muvidDecodePicture);
  muvid_UNLOAD_LIBRARY(*muvidApi, muvidDecodeStatus);
  muvid_UNLOAD_LIBRARY(*muvidApi, muvidReconfigureEncoder);
  muvid_UNLOAD_LIBRARY(*muvidApi, muvidMapVideoFrame);
  muvid_UNLOAD_LIBRARY(*muvidApi, muvidMapVideoFrame64);
  muvid_UNLOAD_LIBRARY(*muvidApi, muvidUnmapVideoFrame);
  muvid_UNLOAD_LIBRARY(*muvidApi, muvidUnmapVideoFrame64);
  muvid_UNLOAD_LIBRARY(*muvidApi, muvidCtxLockCreate);
  muvid_UNLOAD_LIBRARY(*muvidApi, muvidCtxLockDestroy);
  muvid_UNLOAD_LIBRARY(*muvidApi, muvidCtxLock);
  muvid_UNLOAD_LIBRARY(*muvidApi, muvidCtxLockUnlock);
  if (muvid_dlclose(muvidApi->lib) != 0) {
    return "Failed to close library handle";
  };
  return NULL;
}

static bool loadmuvidSymbols(muvidFunctions* muvidApi, const char* file)
{
  const char* err = NULL;
  muvidApi->lib = muvid_dlopen(path);
  if (!lib) {
    return "Failed to open dynamic library";
  }
  muvid_LOAD_LIBRARY(*muvidApi, muvidGetDecoderCaps);
  muvid_LOAD_LIBRARY(*muvidApi, muvidCreateDecoder);
  muvid_LOAD_LIBRARY(*muvidApi, muvidDestroyDecoder);
  muvid_LOAD_LIBRARY(*muvidApi, muvidDecodePicture);
  muvid_LOAD_LIBRARY(*muvidApi, muvidDecodeStatus);
  muvid_LOAD_LIBRARY(*muvidApi, muvidReconfigureEncoder);
  muvid_LOAD_LIBRARY(*muvidApi, muvidMapVideoFrame);
  muvid_LOAD_LIBRARY(*muvidApi, muvidMapVideoFrame64);
  muvid_LOAD_LIBRARY(*muvidApi, muvidUnmapVideoFrame);
  muvid_LOAD_LIBRARY(*muvidApi, muvidUnmapVideoFrame64);
  muvid_LOAD_LIBRARY(*muvidApi, muvidCtxLockCreate);
  muvid_LOAD_LIBRARY(*muvidApi, muvidCtxLockDestroy);
  muvid_LOAD_LIBRARY(*muvidApi, muvidCtxLock);
  muvid_LOAD_LIBRARY(*muvidApi, muvidCtxLockUnlock);

  return NULL;

err:
  unloadmuvidSymbols(muvidApi);
  return err;
}
