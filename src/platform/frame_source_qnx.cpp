// frame_source_qnx.cpp — camapi camera via the workshop's RpiCam, unchanged.
// UNTESTED until it runs on the Pi.
#include <errno.h>

#include <cstdio>

#include "frame_source.hpp"
#include "rpi_cam.hpp"  // third_party/QNX-AI-workshop

namespace {

// Workshop numbering on the RPi 5: CAM/DISP0 = 3, CAM/DISP1 = 4, USB = 5.
constexpr int DEFAULT_UNIT = 5;

class QnxSource : public FrameSource {
 public:
  explicit QnxSource(const CameraConfig& c)
      : cam_((camera_unit_t)(c.unit < 0 ? DEFAULT_UNIT : c.unit)),
        unit_(c.unit < 0 ? DEFAULT_UNIT : c.unit) {}
  ~QnxSource() override { stop(); }

  bool start(FrameCb cb) override {
    if (cam_.init() != EOK) {
      fprintf(stderr, "error: camera unit %d init failed\n", unit_);
      return false;
    }
    started_ = cam_.start(cb) == EOK;
    return started_;
  }
  void stop() override {
    if (started_) cam_.stop();
    started_ = false;
  }
  std::string describe() const override {
    auto [w, h] = cam_.get_frame_size();
    return "camapi unit " + std::to_string(unit_) + " " + std::to_string(w) +
           "x" + std::to_string(h);
  }

 private:
  RpiCam cam_;
  int unit_;
  bool started_ = false;
};

}  // namespace

std::unique_ptr<FrameSource> FrameSource::create(const CameraConfig& cfg) {
  return std::make_unique<QnxSource>(cfg);
}
