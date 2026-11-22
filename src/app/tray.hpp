// tray.hpp — where the pockets are in the camera image.
//
// Pockets are stored in *normalized* image coordinates (0..1) so a layout
// calibrated at 1280x720 on the laptop still means the same thing at 640x480
// on the C270. Persisted with cv::FileStorage (YAML), which exists on QNX's
// OpenCV build too.
#pragma once
#include <opencv2/core.hpp>
#include <string>
#include <vector>

struct Pocket {
  std::string name;
  cv::Rect2f norm;  // x, y, w, h in [0,1]
};

class Tray {
 public:
  Tray();  // default: three pockets side by side across the lower half

  int size() const { return (int)pockets_.size(); }
  const Pocket& pocket(int i) const { return pockets_[i]; }
  void set_pocket(int i, const cv::Rect2f& norm) { pockets_[i].norm = norm; }

  cv::Rect rect_px(int i, cv::Size frame) const;

  /// Index of the pocket containing pixel @p px, or -1.
  int hit(const cv::Point2f& px, cv::Size frame) const;

  bool load(const std::string& path);
  bool save(const std::string& path) const;

 private:
  std::vector<Pocket> pockets_;
};
