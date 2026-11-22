// model.hpp — the one seam between the hand tracker and its inference engine.
//
// The workshop pipeline (handtracking.cpp) only ever needs four things from a
// model: a float NHWC input buffer, invoke(), the float outputs in the order
// the .tflite file declares them, and how many outputs there are. Hiding that
// behind this interface lets the *same* pre/post-processing code and the *same*
// .tflite files run on:
//
//   - QNX / Raspberry Pi 5  -> model_tflite.cpp  (TFLite C++ API + XNNPACK,
//                                                 exactly what the workshop does)
//   - Windows / Linux laptop -> model_cvdnn.cpp  (OpenCV DNN's TFLite importer,
//                                                 no TFLite build needed)
//
// Exactly one backend .cpp is compiled in; CMake picks it.
#pragma once
#include <memory>
#include <string>

class Model {
 public:
  virtual ~Model() = default;

  /// Input tensor, NHWC float32, in_h * in_w * 3 values. Fill it, then invoke().
  virtual float* input() = 0;

  /// Run inference on whatever is currently in input(). false on failure.
  virtual bool invoke() = 0;

  /// Output tensor i (declaration order of the .tflite file), valid until the
  /// next invoke().
  virtual const float* output(int i) const = 0;

  virtual int num_outputs() const = 0;

  /// Human-readable description of the backend (for logs / the overlay).
  virtual std::string backend() const = 0;

  /// Load a .tflite model whose single input is 1 x in_h x in_w x 3 float.
  /// Returns nullptr (and prints why) on failure.
  static std::unique_ptr<Model> load(const std::string& path, int in_w,
                                     int in_h, int threads);
};
