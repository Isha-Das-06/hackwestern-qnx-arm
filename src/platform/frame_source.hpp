// frame_source.hpp — camera abstraction with the same shape as the workshop's
// RpiCam: start(callback) delivers BGR frames on the source's own thread.
//
//   laptop: frame_source_cv.cpp   cv::VideoCapture (webcam index, video file or
//                                 a still image looped — handy for tests)
//   QNX:    frame_source_qnx.cpp  workshop RpiCam (camapi); C270 on USB = unit 5
#pragma once
#include <functional>
#include <memory>
#include <opencv2/core.hpp>
#include <string>

struct CameraConfig {
  int unit = -1;  // webcam index (laptop, default 0) or camapi unit (QNX, default 5)
  int width = 1280, height = 720;  // requested; the driver may pick another
  std::string file;                // laptop only: image or video instead of a camera
};

class FrameSource {
 public:
  using FrameCb = std::function<void(const cv::Mat& bgr)>;
  virtual ~FrameSource() = default;
  virtual bool start(FrameCb cb) = 0;
  virtual void stop() = 0;
  virtual std::string describe() const = 0;

  static std::unique_ptr<FrameSource> create(const CameraConfig& cfg);
};
