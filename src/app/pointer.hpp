// pointer.hpp — where the judge's index fingertip is, smoothed.
//
// Landmark 8 (index tip) jitters a few pixels frame to frame. Averaging the
// last few frames keeps the "which pocket?" answer from flickering at a pocket
// edge. A short tracking dropout (one missed frame) is bridged instead of
// resetting the dwell timer.
#pragma once
#include <deque>
#include <opencv2/core.hpp>

#include "../vision/handtracking.hpp"

// MediaPipe hand landmark indices used in this project.
namespace lm {
constexpr int WRIST = 0;
constexpr int INDEX_MCP = 5;
constexpr int INDEX_TIP = 8;
constexpr int MIDDLE_MCP = 9;
constexpr int MIDDLE_TIP = 12;
constexpr int RING_MCP = 13;
constexpr int RING_TIP = 16;
}  // namespace lm

/// Pointing shape: index finger straight, middle + ring curled. A flat hand,
/// a fist, a peace sign or a hand holding/placing an object fails, so
/// shuffling objects on the tray can't select a pocket by accident.
/// Uses 3D finger bend when the hand has world landmarks (camera-angle
/// independent), else a 2D length rule. Same rule as python/logic.py.
bool is_pointing(const Hand& h);

/// Total bend in degrees (knuckle + both finger joints) of index, middle,
/// ring, from the 3D landmarks. Zeros if the hand has no 3D landmarks.
std::array<float, 3> finger_bends(const Hand& h);

struct PointerConfig {
  int smooth_frames = 5;     // moving average window
  double dropout_ms = 200;   // keep the last position this long if tracking blips
};

// is_pointing() thresholds, 3D (degrees of total finger bend):
constexpr float POINT_INDEX_MAX_BEND = 75.f;   // index straighter than this
constexpr float POINT_OTHERS_MIN_BEND = 90.f;  // middle + ring more bent than this
// 2D fallback: "extension" = tip-to-knuckle distance / palm length.
constexpr float POINT_INDEX_MIN = 0.45f;
constexpr float POINT_OTHERS_MAX = 0.6f;

struct PointerState {
  bool valid = false;  // we have a fingertip position (live or bridged)
  bool live = false;   // a hand was detected this frame
  cv::Point2f tip;     // smoothed index fingertip, image pixels
  bool pointing = false;  // hand is in a pointing shape (majority of recent frames)
};

class PointerTracker {
 public:
  explicit PointerTracker(const PointerConfig& cfg = {}) : cfg_(cfg) {}
  PointerState update(const Hand* hand, double t_ms);

 private:
  PointerConfig cfg_;
  std::deque<cv::Point2f> hist_;
  std::deque<bool> pose_;
  PointerState last_;
  double t_last_seen_ = -1e9;
};
