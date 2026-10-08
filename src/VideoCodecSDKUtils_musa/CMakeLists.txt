# This copyright notice applies to this file only
#
# SPDX-FileCopyrightText: Copyright (c) 2010-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.



cmake_minimum_required(VERSION 3.20)

# The MUSA runtime is installed externally; the repository supplies the MUSA
# video codec interface headers, including the MTENC 13.0 API.
set(MUSA_ROOT "$ENV{MUSA_ROOT}" CACHE PATH "MUSA toolkit installation root")
if("${MUSA_ROOT}" STREQUAL "")
    set(MUSA_ROOT "/usr/local/musa" CACHE PATH "MUSA toolkit installation root" FORCE)
endif()

find_path(MUSA_INCLUDE_DIR NAMES musa.h
    PATHS "${MUSA_ROOT}/include"
    NO_DEFAULT_PATH)
find_path(MUSA_RUNTIME_API_INCLUDE_DIR NAMES musa_runtime_api.h
    PATHS "${MUSA_ROOT}/include"
    NO_DEFAULT_PATH)
find_path(MUSA_RUNTIME_INCLUDE_DIR NAMES musa_runtime.h
    PATHS "${MUSA_ROOT}/include"
    NO_DEFAULT_PATH)
find_library(MUSA_RUNTIME_LIBRARY NAMES musart
    PATHS "${MUSA_ROOT}/lib" "${MUSA_ROOT}/lib64"
    NO_DEFAULT_PATH)
find_library(MUSA_DRIVER_LIBRARY NAMES musa
    PATHS "${MUSA_ROOT}/lib" "${MUSA_ROOT}/lib64"
    NO_DEFAULT_PATH)
if(NOT MUSA_DRIVER_LIBRARY)
    find_library(MUSA_DRIVER_LIBRARY NAMES musa)
endif()
# mtmuvid.h, muviddec.h, and mtEncodeAPI_130.h are repository-owned MUSA
# interface headers under this directory.
set(MUSA_MUVID_INCLUDE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/Interface"
    CACHE PATH "MUSA video codec interface include directory" FORCE)
find_program(MUSA_MCC_EXECUTABLE mcc
    PATHS "${MUSA_ROOT}/bin"
    NO_DEFAULT_PATH)

if(NOT MUSA_INCLUDE_DIR OR NOT MUSA_RUNTIME_API_INCLUDE_DIR OR NOT MUSA_RUNTIME_INCLUDE_DIR OR
   NOT MUSA_RUNTIME_LIBRARY OR NOT MUSA_DRIVER_LIBRARY OR NOT MUSA_MCC_EXECUTABLE)
    message(FATAL_ERROR
        "MUSA runtime development files were not found under '${MUSA_ROOT}'. "
        "Required: musa runtime headers, musart, musa, and mcc. "
        "The repository supplies mtEncodeAPI_130.h, mtmuvid.h, and muviddec.h. "
        "Install the matching MUSA runtime development package or set -DMUSA_ROOT=<path>.")
endif()

get_filename_component(MUSA_LIBRARY_DIR "${MUSA_RUNTIME_LIBRARY}" DIRECTORY)
set(MUSA_RUNTIME_API_INCLUDE_DIR "${MUSA_RUNTIME_API_INCLUDE_DIR}" CACHE PATH "MUSA runtime API include directory" FORCE)
set(MUSA_RUNTIME_INCLUDE_DIR "${MUSA_RUNTIME_INCLUDE_DIR}" CACHE PATH "MUSA runtime include directory" FORCE)
set(MUSA_MUVID_INCLUDE_DIR "${MUSA_MUVID_INCLUDE_DIR}" CACHE PATH "MUSA video codec interface include directory" FORCE)
set(MUSA_RUNTIME_LIBRARY "${MUSA_RUNTIME_LIBRARY}" CACHE FILEPATH "MUSA runtime library" FORCE)
set(MUSA_DRIVER_LIBRARY "${MUSA_DRIVER_LIBRARY}" CACHE FILEPATH "MUSA driver library" FORCE)
set(MUSA_MCC_EXECUTABLE "${MUSA_MCC_EXECUTABLE}" CACHE FILEPATH "MUSA device compiler" FORCE)

function(musa_import_library target library)
    add_library(${target} UNKNOWN IMPORTED GLOBAL)
    set_target_properties(${target} PROPERTIES
        IMPORTED_LOCATION "${library}"
        INTERFACE_INCLUDE_DIRECTORIES "${MUSA_INCLUDE_DIR};${MUSA_RUNTIME_API_INCLUDE_DIR};${MUSA_RUNTIME_INCLUDE_DIR};${MUSA_MUVID_INCLUDE_DIR}")
endfunction()

musa_import_library(MUSA::musart "${MUSA_RUNTIME_LIBRARY}")
musa_import_library(MUSA::musa "${MUSA_DRIVER_LIBRARY}")

function(probe_musa_offload_arch out_var)
    set(_probe_src "${CMAKE_CURRENT_BINARY_DIR}/musa_arch_probe.c")
    set(_probe_bin "${CMAKE_CURRENT_BINARY_DIR}/musa_arch_probe")
    file(WRITE "${_probe_src}"
"#include <stdio.h>
#include <musa_runtime.h>
int main(void) {
    int n = 0;
    if (musaGetDeviceCount(&n) != musaSuccess || n < 1) { return 1; }
    struct musaDeviceProp p;
    if (musaGetDeviceProperties(&p, 0) != musaSuccess) { return 1; }
    printf(\"MUSA_ARCH %d %d\\n\", p.major, p.minor);
    return 0;
}
")
    find_path(MUSART_INCLUDE_DIR musa_runtime_api.h
        PATHS "${MUSA_INCLUDE_DIR}"
        NO_DEFAULT_PATH)
    find_library(MUSART_LIB musart
        PATHS "${MUSA_LIBRARY_DIR}"
        NO_DEFAULT_PATH)
    if(NOT MUSART_INCLUDE_DIR OR NOT MUSART_LIB)
        set(${out_var} "" PARENT_SCOPE)
        return()
    endif()
    get_filename_component(_musart_dir "${MUSART_LIB}" DIRECTORY)
    execute_process(
        COMMAND ${CMAKE_CXX_COMPILER} ${_probe_src} -o ${_probe_bin}
                -I${MUSART_INCLUDE_DIR} -L${_musart_dir} -lmusart
        RESULT_VARIABLE _probe_cc
        OUTPUT_QUIET ERROR_QUIET)
    if(NOT _probe_cc EQUAL 0)
        set(${out_var} "" PARENT_SCOPE)
        return()
    endif()
    execute_process(
        COMMAND ${CMAKE_COMMAND} -E env
                LD_LIBRARY_PATH=${_musart_dir} ${_probe_bin}
        OUTPUT_VARIABLE _probe_out
        ERROR_QUIET OUTPUT_STRIP_TRAILING_WHITESPACE)
    if(_probe_out MATCHES "MUSA_ARCH ([0-9]+) ([0-9]+)")
        set(${out_var} "mp_${CMAKE_MATCH_1}${CMAKE_MATCH_2}" PARENT_SCOPE)
    else()
        set(${out_var} "" PARENT_SCOPE)
    endif()
endfunction()

if(NOT DEFINED CMAKE_MUSA_ARCHITECTURES)
    probe_musa_offload_arch(_probed_musa_arch)
    if(_probed_musa_arch)
        set(CMAKE_MUSA_ARCHITECTURES ${_probed_musa_arch})
        message(STATUS "MUSA offload arch (probed from GPU): ${CMAKE_MUSA_ARCHITECTURES}")
    else()
        set(CMAKE_MUSA_ARCHITECTURES mp_21)
        message(WARNING "MUSA GPU arch probe failed; falling back to ${CMAKE_MUSA_ARCHITECTURES}. "
                "Set -DCMAKE_MUSA_ARCHITECTURES to match the target GPU.")
    endif()
endif()

set(MUSA_OFFLOAD_FLAGS "")
foreach(_musa_arch IN LISTS CMAKE_MUSA_ARCHITECTURES)
    list(APPEND MUSA_OFFLOAD_FLAGS "--offload-arch=${_musa_arch}")
endforeach()

project(VideoCodecSDKUtils LANGUAGES CXX)

set(USE_NVTX $ENV{USE_NVTX})

set(CODEC_SOURCES
 helper_classes/NvCodec/MuvidDecoder/MuvidDecoder.cpp
 helper_classes/NvCodec/MtEncoder/MtEncoder_130.cpp
)
set(CODEC_HDRS
 helper_classes/NvCodec/MuvidDecoder/MuvidDecoder.h
 helper_classes/NvCodec/MtEncoder/MtEncoder_130.h
 helper_classes/Utils/NvCodecUtils.h
 helper_classes/Utils/FFmpegDemuxer.h
 helper_classes/Utils/FFmpegMuxer.h
 helper_classes/Utils/ColorSpace.h
 helper_classes/Utils/FFmpegStreamer.h
 helper_classes/Utils/Logger.h
 helper_classes/Utils/MtEncoderCLIOptions.h
 helper_classes/Utils/muvidFunctions.h
 helper_classes/Utils/muvid_function_pointer.h
 helper_classes/Utils/muvid_dlopen.h
 helper_classes/Utils/muvid_dlopen_unix.cpp
 helper_classes/Utils/muvid_dlopen_windows.cpp
 helper_classes/Utils/
 Interface/configNvEncVer.h
 Interface/mtEncodeAPI_130.h
)

set(COLORSPACE_MUSA_SOURCE ${CMAKE_CURRENT_SOURCE_DIR}/helper_classes/Utils/ColorSpace.mu)
set(COLORSPACE_MUSA_OBJECT ${CMAKE_CURRENT_BINARY_DIR}/ColorSpace.mu.o)
set(MUSA_MCC "${MUSA_MCC_EXECUTABLE}" CACHE FILEPATH "MUSA device compiler")
set(MUSA_MCC_STD_INCLUDE_FLAGS)
foreach(_musa_include_dir IN LISTS CMAKE_CXX_IMPLICIT_INCLUDE_DIRECTORIES)
    list(APPEND MUSA_MCC_STD_INCLUDE_FLAGS -I${_musa_include_dir})
endforeach()
add_custom_command(
    OUTPUT ${COLORSPACE_MUSA_OBJECT}
    COMMAND ${MUSA_MCC}
            -c ${COLORSPACE_MUSA_SOURCE}
            -o ${COLORSPACE_MUSA_OBJECT}
            -std=c++17
            -fPIC
            ${MUSA_OFFLOAD_FLAGS}
            ${MUSA_MCC_STD_INCLUDE_FLAGS}
            -I${MUSA_INCLUDE_DIR}
            -I${MUSA_RUNTIME_API_INCLUDE_DIR}
            -I${MUSA_RUNTIME_INCLUDE_DIR}
            -I${MUSA_MUVID_INCLUDE_DIR}
            -I${CMAKE_CURRENT_SOURCE_DIR}/helper_classes/NvCodec
            -I${CMAKE_CURRENT_SOURCE_DIR}/helper_classes/Utils
            -I${CMAKE_CURRENT_SOURCE_DIR}/Interface
            -I${FFMPEG_DIR}/include
    DEPENDS ${COLORSPACE_MUSA_SOURCE} ${CMAKE_CURRENT_SOURCE_DIR}/helper_classes/Utils/ColorSpace.h
    VERBATIM
)
set_source_files_properties(${COLORSPACE_MUSA_OBJECT} PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)

set(CODEC_MUSA_UTILS
    ${COLORSPACE_MUSA_OBJECT}
)

if(WIN32)
    set(NV_FFMPEG_HDRS ${FFMPEG_DIR}/include)
endif()

include(GenerateExportHeader)

set(MUSA_HOST_COMPILER ${CMAKE_CXX_COMPILER})

set(MUSA_NVCC_FLAGS ${MUSA_NVCC_FLAGS};-gencode arch=compute_50,code=\"sm_50,compute_50\")
# MUSA 11.7 and later is compiled with /MT option (staticaly linked with C runtime), 
# since we are statically linking musart_static.lib with the app, 
# we need to make sure that all .obj files linked are compiled with /MT to avoid linker warning LNK4098
if (WIN32 AND MUSA_VERSION_MAJOR GREATER_EQUAL 11 AND MUSA_VERSION_MINOR GREATER_EQUAL 7)
    set(MUSA_NVCC_FLAGS ${MUSA_NVCC_FLAGS};-Xcompiler /MT)
endif()
if ( CMAKE_COMPILER_IS_GNUCC )
    if(NOT "${MUSA_NVCC_FLAGS}" MATCHES "-std=c\\+\\+11" )
        list(APPEND MUSA_NVCC_FLAGS -std=c++11)
    endif()
endif()

if(MSVC)
    add_definitions(-D_CRT_SECURE_NO_WARNINGS)
endif()

if (WIN32 AND MUSA_VERSION_MAJOR GREATER_EQUAL 11 AND MUSA_VERSION_MINOR GREATER_EQUAL 7)
    target_compile_options(${PROJECT_NAME} PRIVATE "/MT")
endif()

if(WIN32)
	if(${CMAKE_SYSTEM_PROCESSOR} STREQUAL "x86_64")
		add_compile_options("-fstack-protector-strong")
		add_compile_options("-Wall")
		add_compile_options("-Wformat -Wformat=2 -Wconversion -Wimplicit-fallthrough")
		add_compile_options("--fPIC")
	endif()
endif()


add_library(
    VideoCodecSDKUtils
    ${CODEC_SOURCES}
    ${CODEC_HDRS}
    ${NV_FFMPEG_HDRS}
    ${CODEC_MUSA_UTILS}
)

set(TC_VERSION_MAJOR 1)
set(TC_VERSION_MINOR 0)

generate_export_header(VideoCodecSDKUtils)

target_link_libraries(
    VideoCodecSDKUtils
    PUBLIC
        MUSA::musa
        MUSA::musart
)


target_compile_features(VideoCodecSDKUtils PRIVATE cxx_std_17)
set_property(
    TARGET VideoCodecSDKUtils
    PROPERTY
        # required for shared Python modules in case library is build statically on Unix
        POSITION_INDEPENDENT_CODE
        ON
)

set(VIDEO_CODEC_INTERFACE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/Interface"
    CACHE PATH "Path to Video Codec SDK interface headers"
)
target_include_directories(
    VideoCodecSDKUtils
    PUBLIC
        ${MUSA_INCLUDE_DIR}
        ${MUSA_MUVID_INCLUDE_DIR}
        helper_classes/NvCodec
        helper_classes/Utils
        ${VIDEO_CODEC_INTERFACE_DIR}
        ${CMAKE_CURRENT_BINARY_DIR}
)
target_link_directories(VideoCodecSDKUtils PUBLIC ${MUSA_LIBRARY_DIR})


if(UNIX)
    target_link_libraries(VideoCodecSDKUtils PUBLIC pthread)
endif(UNIX)

include(../cmake/ffmpeg.cmake)
target_include_directories(VideoCodecSDKUtils PUBLIC ${NV_FFMPEG_INCLUDE_DIR})
target_link_libraries(VideoCodecSDKUtils PUBLIC ${NV_FFMPEG_LIBRARIES})

option(USE_NVTX "Use NVTX for profiling" FALSE)

if(USE_NVTX)
option(FETCHCONTENT_QUIET OFF)
include(FetchContent)
fetchcontent_declare(
  nvtx_cpp
  URL https://github.com/NVIDIA/NVTX/archive/v3.1.0.tar.gz # Oct 5 2022
  URL_HASH
  SHA256=dc4e4a227d04d3da46ad920dfee5f7599ac8d6b2ee1809c9067110fb1cc71ced
  SOURCE_SUBDIR c
  DOWNLOAD_EXTRACT_TIMESTAMP ON)
fetchcontent_makeavailable(nvtx_cpp)
endif()

if(USE_NVTX)
   target_link_libraries(VideoCodecSDKUtils PRIVATE nvtx3-cpp)
   target_compile_definitions(VideoCodecSDKUtils PRIVATE -DUSE_NVTX=1)
endif()

message(STATUS "HAS_BSF=${HAS_BSF}")

# Create separate targets for each MTENC version
function(create_codec_utils_target VERSION_SUFFIX VERSION_DEFINE)
    set(TARGET_NAME "VideoCodecSDKUtils${VERSION_SUFFIX}")
    
    add_library(${TARGET_NAME}
        ${CODEC_SOURCES}
        ${CODEC_HDRS}
        ${NV_FFMPEG_HDRS}
        ${CODEC_MUSA_UTILS}
    )

    target_compile_definitions(${TARGET_NAME} PRIVATE ${VERSION_DEFINE})
    
    target_link_directories(${TARGET_NAME}
        PUBLIC
            ${MUSA_LIBRARY_DIR}
    )

    target_link_libraries(${TARGET_NAME}
        PUBLIC
            MUSA::musa
            MUSA::musart
    )

    if(UNIX)
        target_link_libraries(${TARGET_NAME} PUBLIC pthread)
    endif()

    target_include_directories(${TARGET_NAME}
        PUBLIC
            ${MUSA_INCLUDE_DIR}
            ${MUSA_MUVID_INCLUDE_DIR}
            helper_classes/NvCodec
            helper_classes/Utils
            ${VIDEO_CODEC_INTERFACE_DIR}
            ${CMAKE_CURRENT_BINARY_DIR}
            ${NV_FFMPEG_INCLUDE_DIR}
    )

    target_link_libraries(${TARGET_NAME} PUBLIC ${NV_FFMPEG_LIBRARIES})

    if(USE_NVTX)
        target_link_libraries(${TARGET_NAME} PRIVATE nvtx3-cpp)
        target_compile_definitions(${TARGET_NAME} PRIVATE -DUSE_NVTX=1)
    endif()

    set_property(TARGET ${TARGET_NAME}
        PROPERTY
            POSITION_INDEPENDENT_CODE ON
    )
endfunction()

# MUSA supports the MTENC 13.0 interface only.
create_codec_utils_target("_130" "MTENC_VER_13_0")
