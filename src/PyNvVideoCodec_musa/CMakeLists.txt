# This copyright notice applies to this file only
#
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

cmake_minimum_required(VERSION 3.21)

project(PyNvVideoCodec VERSION 2.0)

set(PYTHON_MODULE_PREFIX "PyNvVideoCodec")

set(PYNVVIDEOCODEC_VERSION_MAJOR 2)
set(PYNVVIDEOCODEC_VERSION_MINOR 0)

if(POLICY CMP0135)
    cmake_policy(SET CMP0135 NEW)
endif()

set(CMAKE_POLICY_VERSION_MINIMUM 3.5)

configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/inc/Version.hpp.in"
    "${CMAKE_CURRENT_BINARY_DIR}/pynvcode_version.h"
    @ONLY
)


find_package(Python ${REQUESTED_PYTHON_VERSION} COMPONENTS Interpreter Development.Module)

find_package(pybind11 CONFIG REQUIRED)

if(DEMUX_ONLY)
    set(PY_SOURCES
        src/PyNvDemuxer.cpp
        src/NvDemuxer.cpp
    )
    set(PY_HDRS
        inc
        ../VideoCodecSDKUtils_musa/helper_classes/Utils
        ../VideoCodecSDKUtils_musa/Interface
    )
else()
    set(PY_SOURCES
        src/DLPackUtils.cpp
        src/ExternalBuffer.cpp
        src/PyNvVideoCodec.cpp
        src/PyNvDemuxer.cpp
        src/PyMtEncoder.cpp
        src/NvDemuxer.cpp
        src/PyCAIMemoryView.cpp
        src/PyMuvidDecoder.cpp
        src/MtEncoderClInterface.cpp
        src/SimpleDecoder.cpp
        src/PyNvSimpleDecoder.cpp
        src/DecoderCommon.cpp
        src/ThreadedDecoder.cpp
        src/PyNvThreadedDecoder.cpp
        src/PyNvSimpleTranscoder.cpp
        src/SimpleTranscoder.cpp
        src/SeekUtils.cpp
        ../VideoCodecSDKUtils_musa/helper_classes/NvCodec/MtEncoder/MtEncoderCuda.cpp
    )
    set(PY_HDRS
        inc
        ../VideoCodecSDKUtils_musa/helper_classes/NvCodec/MtEncoder
        ${FFMPEG_DIR}/include/
        utils
    )
endif()

# DLPack setup, matching the CUDA backend.
include(FetchContent)
FetchContent_Populate(
    dlpack
    URL        https://github.com/dmlc/dlpack/archive/refs/tags/v0.8.zip
    SOURCE_DIR dlpack
)
message(STATUS " downloading dlpack library ${dlpack_SOURCE_DIR}")

# NVTX setup if needed
if(NOT DEMUX_ONLY AND USE_NVTX)
    message(STATUS "downloading nvtx library")
    option(FETCHCONTENT_QUIET OFF)
    include(FetchContent)
    fetchcontent_declare(
        nvtx_cpp
        URL https://github.com/NVIDIA/NVTX/archive/v3.1.0.tar.gz
        URL_HASH SHA256=dc4e4a227d04d3da46ad920dfee5f7599ac8d6b2ee1809c9067110fb1cc71ced
        SOURCE_SUBDIR c
        DOWNLOAD_EXTRACT_TIMESTAMP ON
    )
    fetchcontent_makeavailable(nvtx_cpp)
endif()

# Function to create PYD target with specific version
function(create_pyd_target VERSION_SUFFIX VERSION_DEFINE)
    set(TARGET_NAME "${PYTHON_MODULE_PREFIX}${VERSION_SUFFIX}")
    pybind11_add_module(${TARGET_NAME} MODULE
        ${PY_SOURCES}
    )

    set_property(TARGET ${TARGET_NAME} PROPERTY CXX_STANDARD 17)
    target_include_directories(${TARGET_NAME}
        PUBLIC
        ${MUSA_INCLUDE_DIR}
        ${MUSA_MUVID_INCLUDE_DIR}
        ${PY_HDRS}
    )

    target_include_directories(${TARGET_NAME} PRIVATE
        "${dlpack_SOURCE_DIR}/include"
    )

    if(DEMUX_ONLY)
        target_compile_definitions(${TARGET_NAME} PUBLIC -DDEMUX_ONLY=1)
    else()
        if(USE_NVTX)
            target_link_libraries(${TARGET_NAME} PRIVATE nvtx3-cpp)
            target_compile_definitions(${TARGET_NAME} PRIVATE -DUSE_NVTX=1)
        endif()
        target_link_libraries(${TARGET_NAME} PUBLIC VideoCodecSDKUtils${VERSION_SUFFIX})
    endif()

    if(DEMUX_ONLY)
        if(NV_FFMPEG_HAS_BSF)
            target_compile_definitions(${TARGET_NAME} PUBLIC -DHAS_BSF=1)
        endif()
        target_include_directories(${TARGET_NAME} PUBLIC ${NV_FFMPEG_INCLUDE_DIR})
        target_link_libraries(${TARGET_NAME} PUBLIC ${NV_FFMPEG_LIBRARIES})
    endif()

    # Add version-specific define
    target_compile_definitions(${TARGET_NAME} PRIVATE ${VERSION_DEFINE})

    set_target_properties(${TARGET_NAME} PROPERTIES
        PREFIX ""
        OUTPUT_NAME "${TARGET_NAME}"
        ARCHIVE_OUTPUT_NAME "${TARGET_NAME}"
        PDB_NAME "${TARGET_NAME}"
        INSTALL_RPATH "$ORIGIN"
        BUILD_WITH_INSTALL_RPATH TRUE
    )

    install(TARGETS ${TARGET_NAME}
        LIBRARY DESTINATION ${PYTHON_MODULE_PREFIX}
        RUNTIME DESTINATION ${PYTHON_MODULE_PREFIX}
        ARCHIVE DESTINATION ${PYTHON_MODULE_PREFIX}
    )
endfunction()

install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/__init__.py"
    DESTINATION ${PYTHON_MODULE_PREFIX}
)

install(DIRECTORY
    "${CMAKE_CURRENT_SOURCE_DIR}/decoders"
    "${CMAKE_CURRENT_SOURCE_DIR}/transcoder"
    DESTINATION ${PYTHON_MODULE_PREFIX}
    FILES_MATCHING PATTERN "*.py"
)

# Set architecture-specific flags
if(UNIX)
    # For Linux, ensure 64-bit build on x86_64 (aarch64 is 64-bit by default)
    if(${CMAKE_SYSTEM_PROCESSOR} STREQUAL "x86_64" OR ${CMAKE_SYSTEM_PROCESSOR} MATCHES "AMD64")
        set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -m64")
        set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -m64")
    endif()
endif()

# MUSA supports the MTENC 13.0 interface only.
create_pyd_target("_130" "MTENC_VER_13_0")

# Create and install VersionCheck module for full builds.
if(NOT DEMUX_ONLY)
    pybind11_add_module(PyVersionCheck MODULE
        ${CMAKE_SOURCE_DIR}/src/NvEncVersionCheck_musa/VersionCheck/NvEncVersionCheck.cpp
    )

    target_include_directories(PyVersionCheck PRIVATE
        ${CMAKE_SOURCE_DIR}/src/NvEncVersionCheck_musa/VersionCheck
        ${MUSA_INCLUDE_DIR}
        ${MUSA_MUVID_INCLUDE_DIR}
    )

    target_link_libraries(PyVersionCheck PRIVATE MUSA::musa MUSA::musart)

    if(UNIX)
        if(${CMAKE_SYSTEM_PROCESSOR} STREQUAL "x86_64" OR ${CMAKE_SYSTEM_PROCESSOR} MATCHES "AMD64")
            target_compile_options(PyVersionCheck PRIVATE -m64)
        endif()
    endif()

    set_target_properties(PyVersionCheck PROPERTIES
        PREFIX ""
        OUTPUT_NAME "VersionCheck"
        ARCHIVE_OUTPUT_NAME "VersionCheck"
        PDB_NAME "VersionCheck"
        INSTALL_RPATH "$ORIGIN"
        BUILD_WITH_INSTALL_RPATH TRUE
    )

    # For Linux, ensure RPATH is set correctly
    if(UNIX)
        set_target_properties(PyVersionCheck PROPERTIES
            INSTALL_RPATH "\$ORIGIN/lib:\$ORIGIN"
            BUILD_WITH_INSTALL_RPATH TRUE
        )
    endif()

    install(TARGETS PyVersionCheck
        LIBRARY DESTINATION ${PYTHON_MODULE_PREFIX}
        RUNTIME DESTINATION ${PYTHON_MODULE_PREFIX}
        ARCHIVE DESTINATION ${PYTHON_MODULE_PREFIX}
    )
endif()

# Install shared libraries
if(WIN32)
    # Windows DLL installation
    install(
        DIRECTORY "${NV_FFMPEG_LIBRARY_DIR}/"
        DESTINATION PyNvVideoCodec
        FILES_MATCHING
        PATTERN "*.dll"
    )
else()
    # Linux .so installation
    install(
        DIRECTORY "${NV_FFMPEG_LIBRARY_DIR}/"
        DESTINATION ${PYTHON_MODULE_PREFIX}
        FILES_MATCHING
        PATTERN "*.so*"
        PATTERN "*.a" EXCLUDE
    )
endif()