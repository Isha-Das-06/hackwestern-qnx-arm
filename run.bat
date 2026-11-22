@echo off
rem Run pickvision on the laptop webcam. Extra options pass through, e.g.
rem   run.bat --cam 1          (use the second camera, e.g. the USB Brio)
rem   run.bat --no-flip        (don't mirror the image)
set PATH=C:\msys64\ucrt64\bin;%PATH%
cd /d "%~dp0"
if not exist build\pickvision.exe call build.bat
build\pickvision.exe %*
