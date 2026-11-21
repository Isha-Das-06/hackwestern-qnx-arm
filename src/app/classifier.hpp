// classifier.hpp — what is sitting in a pocket: empty / egg / cup / block.
//
// Deliberately NOT a neural net (yet). The tray, lighting and three objects
// are fixed, so a few-shot classifier on hand-crafted features is faster to
// train at the venue, runs in well under a millisecond on the Pi, needs no
// extra model file, and is pure OpenCV core/imgproc — which the QNX image has.
//
// How it works:
//   1. Per pocket, a reference photo of the EMPTY pocket is stored ("b" key).
//   2. Foreground = pixels that differ from that reference (Lab colour space).
//      Tiny foreground => Empty, no training needed.
//   3. Otherwise extract rotation-invariant shape + colour features from the
//      largest blob and run k-nearest-neighbours against labelled samples you
//      capture live (keys 1/2/3). Features are pocket-independent, so a sample
//      taken in pocket 1 also teaches pockets 2 and 3.
//
// If this turns out not to be robust enough, swap in a MobileNet .tflite
// through the same Model interface the hand tracker uses (see GAMEPLAN.md).
#pragma once
#include <map>
#include <opencv2/core.hpp>
#include <string>
#include <vector>

enum class Obj : int { Empty = 0, Egg = 1, Cup = 2, Block = 3, Unknown = 4 };
const char* obj_name(Obj o);

struct Prediction {
  Obj cls = Obj::Unknown;
  float conf = 0.f;     // 0..1
  float fg_frac = 0.f;  // fraction of the pocket that differs from empty
  float nn_dist = 0.f;  // distance to nearest training sample (z-units)
};

struct ClassifierConfig {
  float diff_th = 28.f;         // Lab distance counted as "changed"
  float empty_fg_frac = 0.04f;  // below this the pocket is empty
  int k = 3;                    // neighbours
  float reject_dist = 6.0f;     // nearest sample further than this -> Unknown
};

class PocketClassifier {
 public:
  explicit PocketClassifier(const ClassifierConfig& cfg = {}) : cfg_(cfg) {}

  void set_background(int pocket, const cv::Mat& bgr_crop);
  bool has_background(int pocket) const { return bg_.count(pocket) > 0; }

  void add_sample(Obj label, int pocket, const cv::Mat& bgr_crop);
  int num_samples(Obj label) const;
  void clear_samples();

  Prediction predict(int pocket, const cv::Mat& bgr_crop,
                     cv::Mat* debug_mask = nullptr) const;

  bool save(const std::string& path) const;
  bool load(const std::string& path);

 private:
  // Returns false if there is no usable foreground (=> Empty).
  bool features(int pocket, const cv::Mat& bgr_crop, std::vector<float>& f,
                float& fg_frac, cv::Mat* mask_out) const;
  void refit_scaler();

  ClassifierConfig cfg_;
  std::map<int, cv::Mat> bg_;  // normalized-size BGR reference per pocket
  std::vector<std::vector<float>> X_;
  std::vector<int> y_;
  std::vector<float> mu_, sd_;  // per-feature standardisation
};
