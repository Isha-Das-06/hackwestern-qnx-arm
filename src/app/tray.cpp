#include "tray.hpp"

#include <cstdio>

Tray::Tray() {
  const float w = 0.26f, h = 0.32f, y = 0.60f, gap = (1.f - 3 * w) / 4;
  for (int i = 0; i < 3; ++i)
    pockets_.push_back(
        {"P" + std::to_string(i + 1), {gap + i * (w + gap), y, w, h}});
}

cv::Rect Tray::rect_px(int i, cv::Size f) const {
  const auto& n = pockets_[i].norm;
  cv::Rect r(cvRound(n.x * f.width), cvRound(n.y * f.height),
             cvRound(n.width * f.width), cvRound(n.height * f.height));
  return r & cv::Rect({0, 0}, f);
}

int Tray::hit(const cv::Point2f& px, cv::Size f) const {
  for (int i = 0; i < size(); ++i)
    if (rect_px(i, f).contains(cv::Point(cvRound(px.x), cvRound(px.y))))
      return i;
  return -1;
}

bool Tray::load(const std::string& path) {
  cv::FileStorage fs(path, cv::FileStorage::READ);
  if (!fs.isOpened()) return false;
  std::vector<Pocket> out;
  for (const auto& n : fs["pockets"]) {
    Pocket p;
    n["name"] >> p.name;
    std::vector<float> r;
    n["rect"] >> r;
    if (r.size() != 4) continue;
    p.norm = {r[0], r[1], r[2], r[3]};
    out.push_back(p);
  }
  if (out.empty()) return false;
  pockets_ = out;
  return true;
}

bool Tray::save(const std::string& path) const {
  cv::FileStorage fs(path, cv::FileStorage::WRITE);
  if (!fs.isOpened()) {
    fprintf(stderr, "warn: cannot write %s\n", path.c_str());
    return false;
  }
  fs << "pockets" << "[";
  for (const auto& p : pockets_)
    fs << "{" << "name" << p.name << "rect"
       << std::vector<float>{p.norm.x, p.norm.y, p.norm.width, p.norm.height}
       << "}";
  fs << "]";
  return true;
}
