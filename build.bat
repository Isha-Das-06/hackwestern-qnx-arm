@echo off
rem Build pickvision on the laptop (MSYS2 UCRT64 g++ + OpenCV 5).
set PATH=C:\msys64\ucrt64\bin;%PATH%
cd /d "%~dp0"
if not exist build\build.ninja cmake -S . -B build -G Ninja || exit /b 1
cmake --build build
