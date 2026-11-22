// cv_compat.hpp — build against OpenCV 4 (QNX image) and OpenCV 5 (MSYS2).
// OpenCV 5 moved contourArea, minAreaRect, convexHull, invertAffineTransform,
// ... from imgproc into the new geometry module.
#pragma once
#include <opencv2/core/version.hpp>
#include <opencv2/imgproc.hpp>
#if CV_VERSION_MAJOR >= 5
#include <opencv2/geometry.hpp>
#endif
