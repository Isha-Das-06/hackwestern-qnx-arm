// model_cvdnn.cpp — laptop backend: run the same .tflite files through OpenCV
// DNN's TFLite importer, so no TFLite C++ build is needed on Windows.
//
// Two quirks of OpenCV (verified on 5.0 with the MediaPipe lite models):
//  * getUnconnectedOutLayersNames() does not list every output, so outputs
//    are requested by their TFLite tensor names "Identity", "Identity_1", ...
//    which is also their declaration order — the order handtracking.cpp and the
//    TFLite backend use.
//  * The importer expects an NCHW blob even though the model is NHWC, so the
//    NHWC input() buffer is repacked with blobFromImage() before each run.
#include <cstdio>
#include <opencv2/dnn.hpp>
#include <set>

#include "model.hpp"

namespace {

class CvDnnModel : public Model {
 public:
  bool init(const std::string& path, int w, int h) {
    try {
      net_ = cv::dnn::readNetFromTFLite(path, cv::dnn::ENGINE_CLASSIC);
    } catch (const cv::Exception& e) {
      fprintf(stderr, "error: cannot load model %s: %s\n", path.c_str(),
              e.what());
      return false;
    }
    if (net_.empty()) {
      fprintf(stderr, "error: cannot load model %s\n", path.c_str());
      return false;
    }
    auto layers = net_.getLayerNames();
    std::set<std::string> have(layers.begin(), layers.end());
    for (int i = 0;; ++i) {
      std::string n = i == 0 ? "Identity" : "Identity_" + std::to_string(i);
      if (!have.count(n)) break;
      names_.push_back(n);
    }
    if (names_.empty()) {  // not a MediaPipe-style export: best effort
      names_ = net_.getUnconnectedOutLayersNames();
      fprintf(stderr, "warn: %s: no Identity* outputs, using %zu unconnected\n",
              path.c_str(), names_.size());
    }
    in_ = cv::Mat(h, w, CV_32FC3, cv::Scalar::all(0));
    return true;
  }

  float* input() override { return in_.ptr<float>(); }

  bool invoke() override {
    try {
      net_.setInput(cv::dnn::blobFromImage(in_));
      net_.forward(outs_, names_);
      for (auto& o : outs_)
        if (!o.isContinuous()) o = o.clone();
      return true;
    } catch (const cv::Exception& e) {
      fprintf(stderr, "error: inference failed: %s\n", e.what());
      return false;
    }
  }

  const float* output(int i) const override { return outs_[i].ptr<float>(); }
  int num_outputs() const override { return (int)names_.size(); }
  std::string backend() const override { return "opencv-dnn " CV_VERSION; }

 private:
  cv::dnn::Net net_;
  cv::Mat in_;  // HxW CV_32FC3 == NHWC float buffer
  std::vector<std::string> names_;
  std::vector<cv::Mat> outs_;
};

}  // namespace

std::unique_ptr<Model> Model::load(const std::string& path, int in_w, int in_h,
                                   int /*threads*/) {
  auto m = std::make_unique<CvDnnModel>();
  if (!m->init(path, in_w, in_h)) return nullptr;
  return m;
}
