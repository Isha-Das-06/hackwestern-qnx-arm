// model_tflite.cpp — TFLite C++ backend (QNX target). Same calls the QNX AI
// Workshop's handtracking.cpp makes: FlatBufferModel + BuiltinOpResolverWithXNNPACK.
#include <cstdio>

#include "model.hpp"
#include "tensorflow/lite/interpreter.h"
#include "tensorflow/lite/interpreter_builder.h"
#include "tensorflow/lite/kernels/register.h"
#include "tensorflow/lite/model_builder.h"

namespace {

class TfliteModel : public Model {
 public:
  bool init(const std::string& path, int threads) {
    model_ = tflite::FlatBufferModel::BuildFromFile(path.c_str());
    if (!model_) {
      fprintf(stderr, "error: cannot load model %s\n", path.c_str());
      return false;
    }
    tflite::ops::builtin::BuiltinOpResolverWithXNNPACK resolver;
    if (tflite::InterpreterBuilder(*model_, resolver)(&interp_, threads) !=
            kTfLiteOk ||
        !interp_) {
      fprintf(stderr, "error: cannot build interpreter for %s\n", path.c_str());
      return false;
    }
    if (interp_->AllocateTensors() != kTfLiteOk) {
      fprintf(stderr, "error: AllocateTensors failed for %s\n", path.c_str());
      return false;
    }
    return true;
  }

  float* input() override { return interp_->typed_input_tensor<float>(0); }
  bool invoke() override { return interp_->Invoke() == kTfLiteOk; }
  const float* output(int i) const override {
    return interp_->typed_output_tensor<float>(i);
  }
  int num_outputs() const override { return (int)interp_->outputs().size(); }
  std::string backend() const override { return "tflite+xnnpack"; }

 private:
  // The FlatBufferModel must outlive the interpreter: declared first.
  std::unique_ptr<tflite::FlatBufferModel> model_;
  std::unique_ptr<tflite::Interpreter> interp_;
};

}  // namespace

std::unique_ptr<Model> Model::load(const std::string& path, int /*in_w*/,
                                   int /*in_h*/, int threads) {
  auto m = std::make_unique<TfliteModel>();
  if (!m->init(path, threads)) return nullptr;
  return m;
}
