#include "classifier.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include "../vision/cv_compat.hpp"

namespace {

constexpr int NORM_SIDE = 96;  // crops are rescaled so the long side is this

// Number of scalar (standardised) features; must match features().
constexpr int N_SCALAR = 12;
// H x S histogram of the foreground, appended un-standardised.
constexpr int H_BINS = 8, S_BINS = 4;
constexpr float HIST_WEIGHT = 4.f;

cv::Mat normalize_size(const cv::Mat& bgr) {
  float s = (float)NORM_SIDE / std::max(bgr.cols, bgr.rows);
  cv::Mat out;
  cv::resize(bgr, out,
             {std::max(8, cvRound(bgr.cols * s)), std::max(8, cvRound(bgr.rows * s))},
             0, 0, cv::INTER_AREA);
  return out;
}

}  // namespace

const char* obj_name(Obj o) {
  switch (o) {
    case Obj::Empty: return "empty";
    case Obj::Egg: return "egg";
    case Obj::Cup: return "cup";
    case Obj::Block: return "block";
    default: return "unknown";
  }
}

void PocketClassifier::set_background(int pocket, const cv::Mat& crop) {
  bg_[pocket] = normalize_size(crop);
}

bool PocketClassifier::features(int pocket, const cv::Mat& crop_in,
                                std::vector<float>& f, float& fg_frac,
                                cv::Mat* mask_out) const {
  cv::Mat crop = normalize_size(crop_in);
  cv::Mat blur;
  cv::GaussianBlur(crop, blur, {5, 5}, 0);

  // ---- foreground mask ----
  cv::Mat mask;
  auto it = bg_.find(pocket);
  if (it != bg_.end()) {
    cv::Mat bg = it->second;
    if (bg.size() != crop.size()) cv::resize(bg, bg, crop.size());
    cv::Mat bgb, lab_a, lab_b;
    cv::GaussianBlur(bg, bgb, {5, 5}, 0);
    cv::cvtColor(blur, lab_a, cv::COLOR_BGR2Lab);
    cv::cvtColor(bgb, lab_b, cv::COLOR_BGR2Lab);
    cv::Mat a, b, d;
    lab_a.convertTo(a, CV_32F);
    lab_b.convertTo(b, CV_32F);
    d = a - b;
    d = d.mul(d);
    std::vector<cv::Mat> ch;
    cv::split(d, ch);
    // Down-weight lightness so soft shadows from the hand / arm count less
    // than real colour change.
    cv::Mat dist2 = 0.35f * ch[0] + ch[1] + ch[2];
    cv::sqrt(dist2, dist2);
    mask = dist2 > cfg_.diff_th;
  } else {
    // No empty reference: fall back to "saturated or dark/bright vs median".
    // Much weaker — capture backgrounds before relying on this.
    cv::Mat gray;
    cv::cvtColor(blur, gray, cv::COLOR_BGR2GRAY);
    cv::threshold(gray, mask, 0, 255, cv::THRESH_BINARY | cv::THRESH_OTSU);
  }
  cv::morphologyEx(mask, mask, cv::MORPH_OPEN,
                   cv::getStructuringElement(cv::MORPH_ELLIPSE, {3, 3}));
  cv::morphologyEx(mask, mask, cv::MORPH_CLOSE,
                   cv::getStructuringElement(cv::MORPH_ELLIPSE, {7, 7}));

  std::vector<std::vector<cv::Point>> contours;
  cv::findContours(mask.clone(), contours, cv::RETR_EXTERNAL,
                   cv::CHAIN_APPROX_SIMPLE);
  int best = -1;
  double best_area = 0;
  for (int i = 0; i < (int)contours.size(); ++i) {
    double a = cv::contourArea(contours[i]);
    if (a > best_area) best_area = a, best = i;
  }
  const double crop_area = (double)crop.total();
  fg_frac = (float)(best_area / crop_area);

  cv::Mat blob = cv::Mat::zeros(crop.size(), CV_8U);
  if (best >= 0) cv::drawContours(blob, contours, best, 255, cv::FILLED);
  if (mask_out) *mask_out = blob;
  if (best < 0 || fg_frac < cfg_.empty_fg_frac) return false;

  // ---- shape (rotation invariant) ----
  const auto& c = contours[best];
  double peri = cv::arcLength(c, true);
  std::vector<cv::Point> hull;
  cv::convexHull(c, hull);
  double hull_area = std::max(1.0, cv::contourArea(hull));
  cv::RotatedRect rr = cv::minAreaRect(c);
  double rr_area = std::max(1.f, rr.size.area());
  float rr_aspect = std::min(rr.size.width, rr.size.height) /
                    std::max(1.f, std::max(rr.size.width, rr.size.height));
  std::vector<cv::Point> poly;
  cv::approxPolyDP(c, poly, 0.03 * peri, true);

  float circularity = (float)(4 * CV_PI * best_area / std::max(1.0, peri * peri));
  float solidity = (float)(best_area / hull_area);
  float extent = (float)(best_area / rr_area);
  float vertices = std::min<float>((float)poly.size(), 12.f) / 12.f;

  // ---- colour of the blob ----
  cv::Mat hsv;
  cv::cvtColor(blur, hsv, cv::COLOR_BGR2HSV);
  std::vector<cv::Mat> hsv_ch;
  cv::split(hsv, hsv_ch);
  cv::Scalar mean_s = cv::mean(hsv_ch[1], blob);
  cv::Scalar mean_v = cv::mean(hsv_ch[2], blob);
  // Hue is circular: average it as a saturation-weighted unit vector.
  double hx = 0, hy = 0, wsum = 1e-6;
  for (int y = 0; y < hsv.rows; ++y) {
    const uchar* m = blob.ptr<uchar>(y);
    const cv::Vec3b* p = hsv.ptr<cv::Vec3b>(y);
    for (int x = 0; x < hsv.cols; ++x)
      if (m[x]) {
        double ang = p[x][0] * (2 * CV_PI / 180.0), w = p[x][1] / 255.0;
        hx += w * std::cos(ang), hy += w * std::sin(ang), wsum += w;
      }
  }
  hx /= wsum, hy /= wsum;

  // Cup seen from above: a rim ring around a darker/shadowed interior. Compare
  // the brightness of the blob's core with its outer ring.
  cv::Mat core;
  int er = std::max(1, cvRound(0.25 * std::sqrt(best_area / CV_PI)));
  cv::erode(blob, core, cv::getStructuringElement(cv::MORPH_ELLIPSE,
                                                  {2 * er + 1, 2 * er + 1}));
  cv::Mat ring = blob & ~core;
  float v_core = cv::countNonZero(core) ? (float)cv::mean(hsv_ch[2], core)[0] : 0.f;
  float v_ring = cv::countNonZero(ring) ? (float)cv::mean(hsv_ch[2], ring)[0] : 1.f;
  float core_ring = v_core / std::max(1.f, v_ring);

  // Edge density inside the blob (block corners/texture vs smooth egg).
  cv::Mat gray, edges;
  cv::cvtColor(blur, gray, cv::COLOR_BGR2GRAY);
  cv::Canny(gray, edges, 50, 150);
  float edge_density =
      (float)cv::countNonZero(edges & blob) / (float)std::max(1.0, best_area);

  f = {fg_frac,    circularity,           solidity,
       extent,     rr_aspect,             vertices,
       (float)hx,  (float)hy,             (float)mean_s[0] / 255.f,
       (float)mean_v[0] / 255.f, core_ring, edge_density};
  static_assert(N_SCALAR == 12, "update N_SCALAR with the feature list");

  // ---- H x S histogram of the blob ----
  cv::Mat hist;
  int ch_idx[] = {0, 1}, bins[] = {H_BINS, S_BINS};
  float hr[] = {0, 180}, sr[] = {0, 256};
  const float* ranges[] = {hr, sr};
  cv::calcHist(&hsv, 1, ch_idx, blob, hist, 2, bins, ranges);
  hist /= std::max(1.0, cv::sum(hist)[0]);
  for (int i = 0; i < H_BINS * S_BINS; ++i)
    f.push_back(hist.at<float>(i / S_BINS, i % S_BINS));
  return true;
}

void PocketClassifier::add_sample(Obj label, int pocket, const cv::Mat& crop) {
  if (label == Obj::Empty) return;  // empty is decided by the mask rule
  std::vector<float> f;
  float frac;
  if (!features(pocket, crop, f, frac, nullptr)) {
    fprintf(stderr, "sample ignored: pocket %d looks empty (fg=%.3f)\n",
            pocket + 1, frac);
    return;
  }
  X_.push_back(f);
  y_.push_back((int)label);
  refit_scaler();
  printf("sample: %s from pocket %d (now %d)\n", obj_name(label), pocket + 1,
         num_samples(label));
}

int PocketClassifier::num_samples(Obj label) const {
  return (int)std::count(y_.begin(), y_.end(), (int)label);
}

void PocketClassifier::clear_samples() {
  X_.clear();
  y_.clear();
  mu_.clear();
  sd_.clear();
}

void PocketClassifier::refit_scaler() {
  mu_.assign(N_SCALAR, 0.f);
  sd_.assign(N_SCALAR, 1.f);
  if (X_.empty()) return;
  const float n = (float)X_.size();
  for (const auto& x : X_)
    for (int j = 0; j < N_SCALAR; ++j) mu_[j] += x[j] / n;
  std::vector<float> var(N_SCALAR, 0.f);
  for (const auto& x : X_)
    for (int j = 0; j < N_SCALAR; ++j) var[j] += (x[j] - mu_[j]) * (x[j] - mu_[j]) / n;
  // Floor the spread: with few samples a feature can have ~0 variance and
  // would otherwise dominate every distance.
  for (int j = 0; j < N_SCALAR; ++j)
    sd_[j] = std::max(std::sqrt(var[j]), 0.05f);
}

Prediction PocketClassifier::predict(int pocket, const cv::Mat& crop,
                                     cv::Mat* debug_mask) const {
  Prediction p;
  std::vector<float> f;
  if (!features(pocket, crop, f, p.fg_frac, debug_mask)) {
    if (has_background(pocket)) {
      p.cls = Obj::Empty;
      p.conf = 1.f;
    }
    return p;
  }
  if (X_.empty()) return p;  // Unknown until trained

  std::vector<std::pair<float, int>> d;
  d.reserve(X_.size());
  for (size_t i = 0; i < X_.size(); ++i) {
    float s = 0;
    for (int j = 0; j < N_SCALAR; ++j) {
      float z = (f[j] - X_[i][j]) / sd_[j];
      s += z * z;
    }
    for (size_t j = N_SCALAR; j < f.size(); ++j) {
      float z = HIST_WEIGHT * (f[j] - X_[i][j]);
      s += z * z;
    }
    d.push_back({std::sqrt(s), y_[i]});
  }
  int k = std::min<int>(cfg_.k, (int)d.size());
  std::partial_sort(d.begin(), d.begin() + k, d.end());
  int votes[5] = {0};
  for (int i = 0; i < k; ++i) votes[d[i].second]++;
  int best = (int)(std::max_element(votes, votes + 5) - votes);
  p.nn_dist = d[0].first;
  p.conf = (float)votes[best] / k;
  p.cls = p.nn_dist > cfg_.reject_dist ? Obj::Unknown : (Obj)best;
  return p;
}

bool PocketClassifier::save(const std::string& path) const {
  cv::FileStorage fs(path, cv::FileStorage::WRITE);
  if (!fs.isOpened()) return false;
  fs << "backgrounds" << "[";
  for (const auto& [k, m] : bg_) fs << "{" << "pocket" << k << "img" << m << "}";
  fs << "]";
  cv::Mat X((int)X_.size(), X_.empty() ? 0 : (int)X_[0].size(), CV_32F);
  for (int i = 0; i < X.rows; ++i)
    std::copy(X_[i].begin(), X_[i].end(), X.ptr<float>(i));
  fs << "X" << X << "y" << y_;
  return true;
}

bool PocketClassifier::load(const std::string& path) {
  cv::FileStorage fs(path, cv::FileStorage::READ);
  if (!fs.isOpened()) return false;
  bg_.clear();
  for (const auto& n : fs["backgrounds"]) {
    int k;
    cv::Mat m;
    n["pocket"] >> k;
    n["img"] >> m;
    if (!m.empty()) bg_[k] = m;
  }
  cv::Mat X;
  fs["X"] >> X;
  std::vector<int> y;
  fs["y"] >> y;
  clear_samples();
  for (int i = 0; i < X.rows && i < (int)y.size(); ++i) {
    X_.emplace_back(X.ptr<float>(i), X.ptr<float>(i) + X.cols);
    y_.push_back(y[i]);
  }
  refit_scaler();
  return true;
}
