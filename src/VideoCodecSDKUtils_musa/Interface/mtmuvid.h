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

/********************************************************************************************************************/
//! \file mtmuvid.h
//!   MUVIDODE API provides video decoding interface to NVIDIA GPU devices.
//! \date 2015-2022
//!  This file contains the interface constants, structure definitions and function prototypes.
/********************************************************************************************************************/

#if !defined(__MTMUVID_H__)
#define __MTMUVID_H__

#include <muviddec.h>

#if defined(__cplusplus)
extern "C" {
#endif /* __cplusplus */

#define MAX_CLOCK_TS 3

/***********************************************/
//!
//! High-level helper APIs for video sources
//!
/***********************************************/

typedef void *MUvideosource;
typedef void *MUvideoparser;
typedef long long MUvideotimestamp;


/************************************************************************/
//! \enum musaVideoState
//! Video source state enums
//! Used in muvidSetVideoSourceState and muvidGetVideoSourceState APIs
/************************************************************************/
typedef enum {
    musaVideoState_Error   = -1,    /**< Error state (invalid source)                  */
    musaVideoState_Stopped = 0,     /**< Source is stopped (or reached end-of-stream)  */
    musaVideoState_Started = 1      /**< Source is running and delivering data         */
} musaVideoState;

/************************************************************************/
//! \enum musaAudioCodec
//! Audio compression enums
//! Used in MUAUDIOFORMAT structure
/************************************************************************/
typedef enum {
    musaAudioCodec_MPEG1=0,         /**< MPEG-1 Audio               */
    musaAudioCodec_MPEG2,           /**< MPEG-2 Audio               */
    musaAudioCodec_MP3,             /**< MPEG-1 Layer III Audio     */
    musaAudioCodec_AC3,             /**< Dolby Digital (AC3) Audio  */
    musaAudioCodec_LPCM,            /**< PCM Audio                  */
    musaAudioCodec_AAC,             /**< AAC Audio                  */
} musaAudioCodec;

/************************************************************************/
//! \ingroup STRUCTS
//! \struct TIMECODESET
//! Used to store Time code set extracted from H264 and HEVC codecs
/************************************************************************/
typedef struct _TIMECODESET
{
    unsigned int time_offset_value;
    unsigned short n_frames;
    unsigned char clock_timestamp_flag;
    unsigned char units_field_based_flag;
    unsigned char counting_type;
    unsigned char full_timestamp_flag;
    unsigned char discontinuity_flag;
    unsigned char cnt_dropped_flag;
    unsigned char seconds_value;
    unsigned char minutes_value;
    unsigned char hours_value;
    unsigned char seconds_flag;
    unsigned char minutes_flag;
    unsigned char hours_flag;
    unsigned char time_offset_length;
    unsigned char reserved;
} TIMECODESET;

/************************************************************************/
//! \ingroup STRUCTS
//! \struct TIMECODE
//! Used to extract Time code in H264 and HEVC codecs
/************************************************************************/
typedef struct _TIMECODE
{
    TIMECODESET time_code_set[MAX_CLOCK_TS];
    unsigned char num_clock_ts;
} TIMECODE;

/**********************************************************************************/
//! \ingroup STRUCTS
//! \struct SEIMASTERINGDISPLAYINFO
//! Used to extract mastering display color volume SEI in H264 and HEVC codecs
/**********************************************************************************/
typedef struct _SEIMASTERINGDISPLAYINFO
{
    unsigned short display_primaries_x[3];
    unsigned short display_primaries_y[3];
    unsigned short white_point_x;
    unsigned short white_point_y;
    unsigned int max_display_mastering_luminance;
    unsigned int min_display_mastering_luminance;
} SEIMASTERINGDISPLAYINFO;

/**********************************************************************************/
//! \ingroup STRUCTS
//! \struct SEICONTENTLIGHTLEVELINFO
//! Used to extract content light level info SEI in H264 and HEVC codecs
/**********************************************************************************/
typedef struct _SEICONTENTLIGHTLEVELINFO
{
    unsigned short max_content_light_level;
    unsigned short max_pic_average_light_level;
    unsigned int reserved;
} SEICONTENTLIGHTLEVELINFO;

/**********************************************************************************/
//! \ingroup STRUCTS
//! \struct TIMECODEMPEG2
//! Used to extract Time code in MPEG2 codec
/**********************************************************************************/
typedef struct _TIMECODEMPEG2
{
    unsigned char drop_frame_flag;
    unsigned char time_code_hours;
    unsigned char time_code_minutes;
    unsigned char marker_bit;
    unsigned char time_code_seconds;
    unsigned char time_code_pictures;
} TIMECODEMPEG2;

/**********************************************************************************/
//! \ingroup STRUCTS
//! \struct SEIALTERNATIVETRANSFERCHARACTERISTICS
//! Used to extract alternative transfer characteristics SEI in H264 and HEVC codecs
/**********************************************************************************/
typedef struct _SEIALTERNATIVETRANSFERCHARACTERISTICS
{
    unsigned char preferred_transfer_characteristics;
} SEIALTERNATIVETRANSFERCHARACTERISTICS;

/**********************************************************************************/
//! \ingroup STRUCTS
//! \struct MUSEIMESSAGE;
//! Used in MUVIDSEIMESSAGEINFO structure
/**********************************************************************************/
typedef struct _MUSEIMESSAGE
{
    unsigned char sei_message_type; /**< OUT: SEI Message Type      */
    unsigned char reserved[3];
    unsigned int sei_message_size;  /**< OUT: SEI Message Size      */
} MUSEIMESSAGE;

/************************************************************************************************/
//! \ingroup STRUCTS
//! \struct MUVIDEOFORMAT
//! Video format
//! Used in muvidGetSourceVideoFormat API
/************************************************************************************************/
typedef struct
{
    musaVideoCodec codec;                   /**< OUT: Compression format          */
   /**
    * OUT: frame rate = numerator / denominator (for example: 30000/1001)
    */
    struct {
        /**< OUT: frame rate numerator   (0 = unspecified or variable frame rate) */
        unsigned int numerator;
        /**< OUT: frame rate denominator (0 = unspecified or variable frame rate) */
        unsigned int denominator;
    } frame_rate;
    unsigned char progressive_sequence;     /**< OUT: 0=interlaced, 1=progressive                                      */
    unsigned char bit_depth_luma_minus8;    /**< OUT: high bit depth luma. E.g, 2 for 10-bitdepth, 4 for 12-bitdepth   */
    unsigned char bit_depth_chroma_minus8;  /**< OUT: high bit depth chroma. E.g, 2 for 10-bitdepth, 4 for 12-bitdepth */
    unsigned char min_num_decode_surfaces;  /**< OUT: Minimum number of decode surfaces to be allocated for correct
                                                      decoding. The client can send this value in ulNumDecodeSurfaces
                                                      (in MUVIDDECODECREATEINFO structure).
                                                      This guarantees correct functionality and optimal video memory
                                                      usage but not necessarily the best performance, which depends on
                                                      the design of the overall application. The optimal number of
                                                      decode surfaces (in terms of performance and memory utilization)
                                                      should be decided by experimentation for each application, but it
                                                      cannot go below min_num_decode_surfaces.
                                                      If this value is used for ulNumDecodeSurfaces then it must be
                                                      returned to parser during sequence callback.                     */
    unsigned int coded_width;               /**< OUT: coded frame width in pixels                                      */
    unsigned int coded_height;              /**< OUT: coded frame height in pixels                                     */
   /**
    * area of the frame that should be displayed
    * typical example:
    * coded_width = 1920, coded_height = 1088
    * display_area = { 0,0,1920,1080 }
    */
    struct {
        int left;                           /**< OUT: left position of display rect    */
        int top;                            /**< OUT: top position of display rect     */
        int right;                          /**< OUT: right position of display rect   */
        int bottom;                         /**< OUT: bottom position of display rect  */
    } display_area;
    musaVideoChromaFormat chroma_format;    /**< OUT:  Chroma format                   */
    unsigned int bitrate;                   /**< OUT: video bitrate (bps, 0=unknown)   */
   /**
    * OUT: Display Aspect Ratio = x:y (4:3, 16:9, etc)
    */
    struct {
        int x;
        int y;
    } display_aspect_ratio;
    /**
    * Video Signal Description
    * Refer section E.2.1 (VUI parameters semantics) of H264 spec file
    */
    struct {
        unsigned char video_format          : 3; /**< OUT: 0-Component, 1-PAL, 2-NTSC, 3-SECAM, 4-MAC, 5-Unspecified     */
        unsigned char video_full_range_flag : 1; /**< OUT: indicates the black level and luma and chroma range           */
        unsigned char reserved_zero_bits    : 4; /**< Reserved bits                                                      */
        unsigned char color_primaries;           /**< OUT: chromaticity coordinates of source primaries                  */
        unsigned char transfer_characteristics;  /**< OUT: opto-electronic transfer characteristic of the source picture */
        unsigned char matrix_coefficients;       /**< OUT: used in deriving luma and chroma signals from RGB primaries   */
    } video_signal_description;
    unsigned int seqhdr_data_length;             /**< OUT: Additional bytes following (MUVIDEOFORMATEX)                  */
} MUVIDEOFORMAT;

/****************************************************************/
//! \ingroup STRUCTS
//! \struct MUVIDOPERATINGPOINTINFO
//! Operating point information of scalable bitstream
/****************************************************************/
typedef struct 
{
    musaVideoCodec codec;
    union 
    {
        struct
        {
            unsigned char  operating_points_cnt;
            unsigned char  reserved24_bits[3];
            unsigned short operating_points_idc[32];
        } av1;
        unsigned char CodecReserved[1024];
    };
} MUVIDOPERATINGPOINTINFO;

/**********************************************************************************/
//! \ingroup STRUCTS
//! \struct MUVIDSEIMESSAGEINFO
//! Used in muvidParseVideoData API with PFNVIDSEIMSGCALLBACK pfnGetSEIMsg
/**********************************************************************************/
typedef struct _MUVIDSEIMESSAGEINFO
{
    void *pSEIData;                 /**< OUT: SEI Message Data      */
    MUSEIMESSAGE *pSEIMessage;      /**< OUT: SEI Message Info      */
    unsigned int sei_message_count; /**< OUT: SEI Message Count     */
    unsigned int picIdx;            /**< OUT: SEI Message Pic Index */
} MUVIDSEIMESSAGEINFO;

/****************************************************************/
//! \ingroup STRUCTS
//! \struct MUVIDAV1SEQHDR
//! AV1 specific sequence header information
/****************************************************************/
typedef struct {
    unsigned int max_width;
    unsigned int max_height;
    unsigned char reserved[1016];
} MUVIDAV1SEQHDR;

/****************************************************************/
//! \ingroup STRUCTS
//! \struct MUVIDEOFORMATEX
//! Video format including raw sequence header information
//! Used in muvidGetSourceVideoFormat API
/****************************************************************/
typedef struct
{
    MUVIDEOFORMAT format;                 /**< OUT: MUVIDEOFORMAT structure */
    union {
        MUVIDAV1SEQHDR av1;
        unsigned char raw_seqhdr_data[1024];  /**< OUT: Sequence header data    */
    };
} MUVIDEOFORMATEX;

/****************************************************************/
//! \ingroup STRUCTS
//! \struct MUAUDIOFORMAT
//! Audio formats
//! Used in muvidGetSourceAudioFormat API
/****************************************************************/
typedef struct
{
    musaAudioCodec codec;       /**< OUT: Compression format                                              */
    unsigned int channels;      /**< OUT: number of audio channels                                        */
    unsigned int samplespersec; /**< OUT: sampling frequency                                              */
    unsigned int bitrate;       /**< OUT: For uncompressed, can also be used to determine bits per sample */
    unsigned int reserved1;     /**< Reserved for future use                                              */
    unsigned int reserved2;     /**< Reserved for future use                                              */
} MUAUDIOFORMAT;


/***************************************************************/
//! \enum MUvideopacketflags
//! Data packet flags
//! Used in MUVIDSOURCEDATAPACKET structure
/***************************************************************/
typedef enum {
    MUVID_PKT_ENDOFSTREAM   = 0x01,   /**< Set when this is the last packet for this stream                              */
    MUVID_PKT_TIMESTAMP     = 0x02,   /**< Timestamp is valid                                                            */
    MUVID_PKT_DISCONTINUITY = 0x04,   /**< Set when a discontinuity has to be signalled                                  */
    MUVID_PKT_ENDOFPICTURE  = 0x08,   /**< Set when the packet contains exactly one frame or one field                   */
    MUVID_PKT_NOTIFY_EOS    = 0x10,   /**< If this flag is set along with MUVID_PKT_ENDOFSTREAM, an additional (dummy)
                                           display callback will be invoked with null value of MUVIDPARSERDISPINFO which
                                           should be interpreted as end of the stream.                                   */
} MUvideopacketflags;

/*****************************************************************************/
//! \ingroup STRUCTS
//! \struct MUVIDSOURCEDATAPACKET
//! Data Packet
//! Used in muvidParseVideoData API
//! IN for muvidParseVideoData
/*****************************************************************************/
typedef struct _MUVIDSOURCEDATAPACKET
{
    unsigned long flags;            /**< IN: Combination of MUVID_PKT_XXX flags                              */
    unsigned long payload_size;     /**< IN: number of bytes in the payload (may be zero if EOS flag is set) */
    const unsigned char *payload;   /**< IN: Pointer to packet payload data (may be NULL if EOS flag is set) */
    MUvideotimestamp timestamp;     /**< IN: Presentation time stamp (10MHz clock), only valid if
                                             MUVID_PKT_TIMESTAMP flag is set                                 */
} MUVIDSOURCEDATAPACKET;

// Callback for packet delivery
typedef int (MUSAAPI *PFNVIDSOURCECALLBACK)(void *, MUVIDSOURCEDATAPACKET *);

/**************************************************************************************************************************/
//! \ingroup STRUCTS
//! \struct MUVIDSOURCEPARAMS
//! Describes parameters needed in muvidCreateVideoSource API
//! MUVIDODE API is intended for HW accelerated video decoding so MUvideosource doesn't have audio demuxer for all supported
//! containers. It's recommended to clients to use their own or third party demuxer if audio support is needed.
/**************************************************************************************************************************/
typedef struct _MUVIDSOURCEPARAMS
{
    unsigned int ulClockRate;                   /**< IN: Time stamp units in Hz (0=default=10000000Hz)      */
    unsigned int bAnnexb : 1;                   /**< IN: AV1 annexB stream                                  */
    unsigned int uReserved : 31;                /**< Reserved for future use - set to zero                  */
    unsigned int uReserved1[6];                 /**< Reserved for future use - set to zero                  */
    void *pUserData;                            /**< IN: User private data passed in to the data handlers   */
    PFNVIDSOURCECALLBACK pfnVideoDataHandler;   /**< IN: Called to deliver video packets                    */
    PFNVIDSOURCECALLBACK pfnAudioDataHandler;   /**< IN: Called to deliver audio packets.                   */
    void *pvReserved2[8];                       /**< Reserved for future use - set to NULL                  */
} MUVIDSOURCEPARAMS;


/**********************************************/
//! \ingroup ENUMS
//! \enum MUvideosourceformat_flags
//! MUvideosourceformat_flags
//! Used in muvidGetSourceVideoFormat API
/**********************************************/
typedef enum {
    MUVID_FMT_EXTFORMATINFO = 0x100             /**< Return extended format structure (MUVIDEOFORMATEX) */
} MUvideosourceformat_flags;

#if !defined(__APPLE__)
/***************************************************************************************************************************/
//! \ingroup FUNCTS
//! \fn MUresult MUSAAPI muvidCreateVideoSource(MUvideosource *pObj, const char *pszFileName, MUVIDSOURCEPARAMS *pParams)
//! Create MUvideosource object. MUvideosource spawns demultiplexer thread that provides two callbacks: 
//! pfnVideoDataHandler() and pfnAudioDataHandler()
//! MUVIDODE API is intended for HW accelerated video decoding so MUvideosource doesn't have audio demuxer for all supported 
//! containers. It's recommended to clients to use their own or third party demuxer if audio support is needed.
/***************************************************************************************************************************/
MUresult MUSAAPI muvidCreateVideoSource(MUvideosource *pObj, const char *pszFileName, MUVIDSOURCEPARAMS *pParams);

/***************************************************************************************************************************/
//! \ingroup FUNCTS
//! \fn MUresult MUSAAPI muvidCreateVideoSourceW(MUvideosource *pObj, const wchar_t *pwszFileName, MUVIDSOURCEPARAMS *pParams)
//! Create video source
/***************************************************************************************************************************/
MUresult MUSAAPI muvidCreateVideoSourceW(MUvideosource *pObj, const wchar_t *pwszFileName, MUVIDSOURCEPARAMS *pParams);

/********************************************************************/
//! \ingroup FUNCTS
//! \fn MUresult MUSAAPI muvidDestroyVideoSource(MUvideosource obj)
//! Destroy video source
/********************************************************************/
MUresult MUSAAPI muvidDestroyVideoSource(MUvideosource obj);

/******************************************************************************************/
//! \ingroup FUNCTS
//! \fn MUresult MUSAAPI muvidSetVideoSourceState(MUvideosource obj, musaVideoState state)
//! Set video source state to:
//! musaVideoState_Started - to signal the source to run and deliver data
//! musaVideoState_Stopped - to stop the source from delivering the data
//! musaVideoState_Error   - invalid source
/******************************************************************************************/
MUresult MUSAAPI muvidSetVideoSourceState(MUvideosource obj, musaVideoState state);

/******************************************************************************************/
//! \ingroup FUNCTS
//! \fn musaVideoState MUSAAPI muvidGetVideoSourceState(MUvideosource obj)
//! Get video source state
//! Returns:
//! musaVideoState_Started - if Source is running and delivering data
//! musaVideoState_Stopped - if Source is stopped or reached end-of-stream
//! musaVideoState_Error   - if Source is in error state
/******************************************************************************************/
musaVideoState MUSAAPI muvidGetVideoSourceState(MUvideosource obj);

/******************************************************************************************************************/
//! \ingroup FUNCTS
//! \fn MUresult MUSAAPI muvidGetSourceVideoFormat(MUvideosource obj, MUVIDEOFORMAT *pvidfmt, unsigned int flags)
//! Gets video source format in pvidfmt, flags is set to combination of MUvideosourceformat_flags as per requirement
/******************************************************************************************************************/
MUresult MUSAAPI muvidGetSourceVideoFormat(MUvideosource obj, MUVIDEOFORMAT *pvidfmt, unsigned int flags);

/**************************************************************************************************************************/
//! \ingroup FUNCTS
//! \fn MUresult MUSAAPI muvidGetSourceAudioFormat(MUvideosource obj, MUAUDIOFORMAT *paudfmt, unsigned int flags)
//! Get audio source format
//! MUVIDODE API is intended for HW accelerated video decoding so MUvideosource doesn't have audio demuxer for all supported 
//! containers. It's recommended to clients to use their own or third party demuxer if audio support is needed.
/**************************************************************************************************************************/
MUresult MUSAAPI muvidGetSourceAudioFormat(MUvideosource obj, MUAUDIOFORMAT *paudfmt, unsigned int flags);

#endif
/**********************************************************************************/
//! \ingroup STRUCTS
//! \struct MUVIDPARSERDISPINFO
//! Used in muvidParseVideoData API with PFNVIDDISPLAYCALLBACK pfnDisplayPicture
/**********************************************************************************/
typedef struct _MUVIDPARSERDISPINFO
{
    int picture_index;          /**< OUT: Index of the current picture                                                         */
    int progressive_frame;      /**< OUT: 1 if progressive frame; 0 otherwise                                                  */
    int top_field_first;        /**< OUT: 1 if top field is displayed first; 0 otherwise                                       */
    int repeat_first_field;     /**< OUT: Number of additional fields (1=ivtc, 2=frame doubling, 4=frame tripling, 
                                     -1=unpaired field)                                                                        */
    MUvideotimestamp timestamp; /**< OUT: Presentation time stamp                                                              */
} MUVIDPARSERDISPINFO;

/***********************************************************************************************************************/
//! Parser callbacks
//! The parser will call these synchronously from within muvidParseVideoData(), whenever there is sequence change or a picture
//! is ready to be decoded and/or displayed. First argument in functions is "void *pUserData" member of structure MUVIDSOURCEPARAMS
//! Return values from these callbacks are interpreted as below. If the callbacks return failure, it will be propagated by
//! muvidParseVideoData() to the application.
//! Parser picks default operating point as 0 and outputAllLayers flag as 0 if PFNVIDOPPOINTCALLBACK is not set or return value is 
//! -1 or invalid operating point.
//! PFNVIDSEQUENCECALLBACK : 0: fail, 1: succeeded, > 1: override dpb size of parser (set by MUVIDPARSERPARAMS::ulMaxNumDecodeSurfaces
//! while creating parser)
//! PFNVIDDECODECALLBACK   : 0: fail, >=1: succeeded
//! PFNVIDDISPLAYCALLBACK  : 0: fail, >=1: succeeded
//! PFNVIDOPPOINTCALLBACK  : <0: fail, >=0: succeeded (bit 0-9: OperatingPoint, bit 10-10: outputAllLayers, bit 11-30: reserved)
//! PFNVIDSEIMSGCALLBACK   : 0: fail, >=1: succeeded
/***********************************************************************************************************************/
typedef int (MUSAAPI *PFNVIDSEQUENCECALLBACK)(void *, MUVIDEOFORMAT *);
typedef int (MUSAAPI *PFNVIDDECODECALLBACK)(void *, MUVIDPICPARAMS *);
typedef int (MUSAAPI *PFNVIDDISPLAYCALLBACK)(void *, MUVIDPARSERDISPINFO *);
typedef int (MUSAAPI *PFNVIDOPPOINTCALLBACK)(void *, MUVIDOPERATINGPOINTINFO*);
typedef int (MUSAAPI *PFNVIDSEIMSGCALLBACK) (void *, MUVIDSEIMESSAGEINFO *);

/**************************************/
//! \ingroup STRUCTS
//! \struct MUVIDPARSERPARAMS
//! Used in muvidCreateVideoParser API
/**************************************/
typedef struct _MUVIDPARSERPARAMS
{
    musaVideoCodec CodecType;                   /**< IN: musaVideoCodec_XXX                                                  */
    unsigned int ulMaxNumDecodeSurfaces;        /**< IN: Max # of decode surfaces (parser will cycle through these)          */
    unsigned int ulClockRate;                   /**< IN: Timestamp units in Hz (0=default=10000000Hz)                        */
    unsigned int ulErrorThreshold;              /**< IN: % Error threshold (0-100) for calling pfnDecodePicture (100=always 
                                                     IN: call pfnDecodePicture even if picture bitstream is fully corrupted) */
    unsigned int ulMaxDisplayDelay;             /**< IN: Max display queue delay (improves pipelining of decode with display)
                                                         0=no delay (recommended values: 2..4)                               */
    unsigned int bAnnexb : 1;                   /**< IN: AV1 annexB stream                                                   */
    unsigned int uReserved : 31;                /**< Reserved for future use - set to zero                                   */
    unsigned int uReserved1[4];                 /**< IN: Reserved for future use - set to 0                                  */
    void *pUserData;                            /**< IN: User data for callbacks                                             */
    PFNVIDSEQUENCECALLBACK pfnSequenceCallback; /**< IN: Called before decoding frames and/or whenever there is a fmt change */
    PFNVIDDECODECALLBACK pfnDecodePicture;      /**< IN: Called when a picture is ready to be decoded (decode order)         */
    PFNVIDDISPLAYCALLBACK pfnDisplayPicture;    /**< IN: Called whenever a picture is ready to be displayed (display order)  */
    PFNVIDOPPOINTCALLBACK pfnGetOperatingPoint; /**< IN: Called from AV1 sequence header to get operating point of a AV1 
                                                         scalable bitstream                                                  */
    PFNVIDSEIMSGCALLBACK pfnGetSEIMsg;          /**< IN: Called when all SEI messages are parsed for particular frame        */
    void *pvReserved2[5];                       /**< Reserved for future use - set to NULL                                   */
    MUVIDEOFORMATEX *pExtVideoInfo;             /**< IN: [Optional] sequence header data from system layer                   */
} MUVIDPARSERPARAMS;

/************************************************************************************************/
//! \ingroup FUNCTS
//! \fn MUresult MUSAAPI muvidCreateVideoParser(MUvideoparser *pObj, MUVIDPARSERPARAMS *pParams)
//! Create video parser object and initialize
/************************************************************************************************/
MUresult MUSAAPI muvidCreateVideoParser(MUvideoparser *pObj, MUVIDPARSERPARAMS *pParams);

/************************************************************************************************/
//! \ingroup FUNCTS
//! \fn MUresult MUSAAPI muvidParseVideoData(MUvideoparser obj, MUVIDSOURCEDATAPACKET *pPacket)
//! Parse the video data from source data packet in pPacket 
//! Extracts parameter sets like SPS, PPS, bitstream etc. from pPacket and 
//! calls back pfnDecodePicture with MUVIDPICPARAMS data for kicking of HW decoding
//! calls back pfnSequenceCallback with MUVIDEOFORMAT data for initial sequence header or when
//! the decoder encounters a video format change
//! calls back pfnDisplayPicture with MUVIDPARSERDISPINFO data to display a video frame
/************************************************************************************************/
MUresult MUSAAPI muvidParseVideoData(MUvideoparser obj, MUVIDSOURCEDATAPACKET *pPacket);

/************************************************************************************************/
//! \ingroup FUNCTS
//! \fn MUresult MUSAAPI muvidDestroyVideoParser(MUvideoparser obj)
//! Destroy the video parser
/************************************************************************************************/
MUresult MUSAAPI muvidDestroyVideoParser(MUvideoparser obj);

/**********************************************************************************************/

#if defined(__cplusplus)
}
#endif /* __cplusplus */

#endif // __MTMUVID_H__


