@echo off
ffmpeg -hwaccel cuda -hwaccel_output_format cuda -i oo2_overlayed_h264.mp4 -c:v hevc_nvenc -c:a libmp3lame oo2_overlayed_hevc.flv
ffmpeg -hwaccel cuda -hwaccel_output_format cuda -i oo2_overlayed_h264.mp4 -c:v hevc_nvenc -c:a libmp3lame oo2_overlayed_hevc.mov
ffmpeg -hwaccel cuda -hwaccel_output_format cuda -i oo2_overlayed_h264.mp4 -c:v hevc_nvenc -c:a libmp3lame oo2_overlayed_hevc.mp4
ffmpeg -hwaccel cuda -hwaccel_output_format cuda -i oo2_overlayed_h264.mp4 -c:v hevc_nvenc -c:a libmp3lame oo2_overlayed_hevc.mp4

ffmpeg -hwaccel cuda -hwaccel_output_format cuda -i oo2_overlayed_h264.mp4 -c:v av1_nvenc -c:a libmp3lame oo2_overlayed_av1.flv
ffmpeg -hwaccel cuda -hwaccel_output_format cuda -i oo2_overlayed_h264.mp4 -c:v av1_nvenc -c:a libmp3lame oo2_overlayed_av1.mov
ffmpeg -hwaccel cuda -hwaccel_output_format cuda -i oo2_overlayed_h264.mp4 -c:v av1_nvenc -c:a libmp3lame oo2_overlayed_av1.mp4
ffmpeg -hwaccel cuda -hwaccel_output_format cuda -i oo2_overlayed_h264.mp4 -c:v av1_nvenc -c:a libmp3lame oo2_overlayed_av1.mp4
