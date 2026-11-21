#include <atomic>
#include <chrono>
#include <cstdio>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/videoio.hpp>
#include <thread>

#include "frame_source.hpp"

namespace {

class CvSource : public FrameSource {
 public:
  explicit CvSource(const CameraConfig& c) : cfg_(c) {}
  ~CvSource() override { stop(); }

  bool start(FrameCb cb) override {
    if (!cfg_.file.empty()) {
      still_ = cv::imread(cfg_.file);
      if (still_.empty() && !cap_.open(cfg_.file)) {
        fprintf(stderr, "error: cannot open %s\n", cfg_.file.c_str());
        return false;
      }
    } else {
      int idx = cfg_.unit < 0 ? 0 : cfg_.unit;
#ifdef _WIN32
      // DirectShow opens most webcams faster than MSMF and honours the size.
      if (!cap_.open(idx, cv::CAP_DSHOW)) cap_.open(idx);
#else
      cap_.open(idx);
#endif
      if (!cap_.isOpened()) {
        fprintf(stderr, "error: cannot open webcam %d\n", idx);
        return false;
      }
      cap_.set(cv::CAP_PROP_FRAME_WIDTH, cfg_.width);
      cap_.set(cv::CAP_PROP_FRAME_HEIGHT, cfg_.height);
      cap_.set(cv::CAP_PROP_BUFFERSIZE, 1);  // newest frame, not a backlog
    }
    run_ = true;
    th_ = std::thread([this, cb] {
      cv::Mat f;
      while (run_) {
        if (!still_.empty()) {
          cb(still_);
          std::this_thread::sleep_for(std::chrono::milliseconds(33));
          continue;
        }
        if (!cap_.read(f) || f.empty()) {
          if (!cfg_.file.empty()) {  // video file: loop
            cap_.set(cv::CAP_PROP_POS_FRAMES, 0);
            continue;
          }
          std::this_thread::sleep_for(std::chrono::milliseconds(5));
          continue;
        }
        cb(f);
      }
    });
    return true;
  }

  void stop() override {
    run_ = false;
    if (th_.joinable()) th_.join();
    cap_.release();
  }

  std::string describe() const override {
    if (!still_.empty()) return "image " + cfg_.file;
    if (!cfg_.file.empty()) return "video " + cfg_.file;
    return "webcam " + std::to_string(cfg_.unit < 0 ? 0 : cfg_.unit) + " " +
           std::to_string((int)cap_.get(cv::CAP_PROP_FRAME_WIDTH)) + "x" +
           std::to_string((int)cap_.get(cv::CAP_PROP_FRAME_HEIGHT));
  }

 private:
  CameraConfig cfg_;
  cv::VideoCapture cap_;
  cv::Mat still_;
  std::atomic<bool> run_{false};
  std::thread th_;
};

}  // namespace

std::unique_ptr<FrameSource> FrameSource::create(const CameraConfig& cfg) {
  return std::make_unique<CvSource>(cfg);
}
