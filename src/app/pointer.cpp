#include "pointer.hpp"

#include <algorithm>
#include <cmath>

namespace {
float dist(const cv::Point2f& a, const cv::Point2f& b) {
  return std::hypot(a.x - b.x, a.y - b.y);
}
}  // namespace

namespace {
// Degrees the path a->b->c turns at b (0 = straight on).
float turn_deg(const cv::Point3f& a, const cv::Point3f& b, const cv::Point3f& c) {
  cv::Point3f u = b - a, v = c - b;
  double nu = cv::norm(u), nv = cv::norm(v);
  if (nu < 1e-9 || nv < 1e-9) return 0.f;
  double cs = std::clamp(u.dot(v) / (nu * nv), -1.0, 1.0);
  return (float)(std::acos(cs) * 180.0 / CV_PI);
}
}  // namespace

std::array<float, 3> finger_bends(const Hand& h) {
  std::array<float, 3> out{0.f, 0.f, 0.f};
  if (!h.has_world) return out;
  const auto& w = h.world;
  const int mcp[3] = {5, 9, 13};  // index, middle, ring
  for (int f = 0; f < 3; ++f) {
    int m = mcp[f];
    out[f] = turn_deg(w[lm::WRIST], w[m], w[m + 1]) +
             turn_deg(w[m], w[m + 1], w[m + 2]) +
             turn_deg(w[m + 1], w[m + 2], w[m + 3]);
  }
  return out;
}

bool is_pointing(const Hand& h) {
  if (h.has_world) {
    auto b = finger_bends(h);
    return b[0] < POINT_INDEX_MAX_BEND &&
           std::min(b[1], b[2]) > POINT_OTHERS_MIN_BEND;
  }
  const auto& p = h.pts;
  float palm = dist(p[lm::WRIST], p[lm::MIDDLE_MCP]);
  if (palm < 1.f) return false;
  float idx = dist(p[lm::INDEX_TIP], p[lm::INDEX_MCP]) / palm;
  float mid = dist(p[lm::MIDDLE_TIP], p[lm::MIDDLE_MCP]) / palm;
  float ring = dist(p[lm::RING_TIP], p[lm::RING_MCP]) / palm;
  return idx > POINT_INDEX_MIN && std::max(mid, ring) < POINT_OTHERS_MAX * idx;
}

PointerState PointerTracker::update(const Hand* hand, double t_ms) {
  if (!hand) {
    // Bridge short dropouts so a single missed frame doesn't reset the dwell.
    if (last_.valid && t_ms - t_last_seen_ <= cfg_.dropout_ms) {
      PointerState s = last_;
      s.live = false;
      return s;
    }
    hist_.clear();
    pose_.clear();
    last_ = {};
    return last_;
  }
  hist_.push_back(hand->pts[lm::INDEX_TIP]);
  while ((int)hist_.size() > cfg_.smooth_frames) hist_.pop_front();
  pose_.push_back(is_pointing(*hand));
  while ((int)pose_.size() > cfg_.smooth_frames) pose_.pop_front();
  int n_point = 0;
  for (bool b : pose_) n_point += b;
  last_.pointing = n_point * 2 > (int)pose_.size();
  cv::Point2f sum(0, 0);
  for (const auto& p : hist_) sum += p;
  last_.valid = last_.live = true;
  last_.tip = sum * (1.f / hist_.size());
  t_last_seen_ = t_ms;
  return last_;
}
