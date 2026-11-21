cmake_minimum_required(VERSION 3.16)
project(pickvision CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# One source tree, two targets:
#   laptop (Windows/Linux/macOS): OpenCV DNN runs the .tflite models,
#                                 cv::VideoCapture webcam, simulated robot.
#   QNX (Raspberry Pi 5):         TFLite C++ + XNNPACK, camapi camera,
#                                 QNX message passing to the control task.
if(CMAKE_SYSTEM_NAME STREQUAL "QNX")
  set(PV_QNX_DEFAULT ON)
else()
  set(PV_QNX_DEFAULT OFF)
endif()
option(PV_QNX "Build for QNX (TFLite + camapi + MsgSend)" ${PV_QNX_DEFAULT})

find_package(OpenCV REQUIRED)

# Window/keyboard UI needs highgui; the QNX image may not have it.
if(TARGET opencv_highgui AND NOT PV_QNX)
  set(PV_GUI_DEFAULT ON)
else()
  set(PV_GUI_DEFAULT OFF)
endif()
option(PV_GUI "OpenCV highgui window" ${PV_GUI_DEFAULT})

set(SRC
  src/main.cpp
  src/vision/handtracking.cpp
  src/app/pointer.cpp
  src/app/tray.cpp
  src/app/classifier.cpp
  src/app/selector.cpp
)

if(PV_QNX)
  set(WS ${CMAKE_CURRENT_SOURCE_DIR}/third_party/QNX-AI-workshop)
  list(APPEND SRC
    src/vision/model_tflite.cpp
    src/platform/frame_source_qnx.cpp
    src/ipc/control_link_qnx.cpp
    ${WS}/rpi_cam.cpp)
else()
  list(APPEND SRC
    src/vision/model_cvdnn.cpp
    src/platform/frame_source_cv.cpp
    src/ipc/control_link_sim.cpp)
endif()

add_executable(pickvision ${SRC})
target_include_directories(pickvision PRIVATE src ${OpenCV_INCLUDE_DIRS})
target_link_libraries(pickvision PRIVATE ${OpenCV_LIBS})
find_package(Threads REQUIRED)
target_link_libraries(pickvision PRIVATE Threads::Threads)

if(PV_GUI)
  target_compile_definitions(pickvision PRIVATE PV_GUI=1)
endif()

if(PV_QNX)
  target_compile_definitions(pickvision PRIVATE PV_QNX=1)
  target_include_directories(pickvision PRIVATE ${WS})
  find_library(TFLITE_LIB tensorflow-lite REQUIRED)
  target_link_libraries(pickvision PRIVATE ${TFLITE_LIB} camapi)
  # Same workaround the workshop needs for the image's flatbuffers headers.
  target_compile_options(pickvision PRIVATE -include ${WS}/flatbuffers_version_shim.hpp)

  # Minimal control-task stand-in for integration tests on the Pi.
  add_executable(ctrl_stub tools/ctrl_stub_qnx.cpp)
  target_include_directories(ctrl_stub PRIVATE src)
endif()

# Fetch the MediaPipe models if missing (same source as the workshop).
foreach(m palm_detection_lite hand_landmark_lite)
  set(f ${CMAKE_CURRENT_SOURCE_DIR}/models/${m}.tflite)
  if(NOT EXISTS ${f})
    message(STATUS "Downloading ${m}.tflite")
    file(DOWNLOAD https://storage.googleapis.com/mediapipe-assets/${m}.tflite ${f}
         STATUS st)
    list(GET st 0 code)
    if(NOT code EQUAL 0)
      file(REMOVE ${f})
      message(FATAL_ERROR "download of ${m}.tflite failed: ${st}")
    endif()
  endif()
endforeach()
