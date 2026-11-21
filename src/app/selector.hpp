// selector.hpp — turns "point at a pocket for ~1 s" into exactly one pick.
//
//   Idle ──fingertip over a pocket──▶ Dwelling ──held dwell_ms──▶ AwaitClear
//    ▲            │ moved off / to another pocket                    │ hand off pocket
//    │            ▼                                                  ▼
//    ├──────── (reset)                                          Classifying
//    │                                                               │ N-frame vote
//    ├──── Rejected (empty / unknown) ◀──────────────────────────────┤
//    └──── Dispatched ── robot back to idle ◀──── send ──────────────┘
//
// Design points:
//  * Dwell, not a gesture: the judge just holds a finger over the pocket.
//  * The object is classified only once the hand is OFF the pocket (the hand
//    covers the object while pointing), by majority vote over several frames,
//    so one bad frame can't pick the wrong grip strength.
//  * After a selection, that pocket can't re-trigger until the finger leaves
//    it, so a judge who keeps pointing doesn't queue a second pick.
#pragma once
#include <deque>
#include <string>

#include "classifier.hpp"

enum class SelState { Idle, Dwelling, AwaitClear, Classifying, Dispatched, Rejected };
const char* sel_state_name(SelState s);

struct SelectorConfig {
  double dwell_ms = 1000;          // finger must stay on the pocket this long
  int clear_frames = 3;            // pocket must be unoccluded this many frames
  int vote_frames = 5;             // predictions in the majority vote
  double await_timeout_ms = 8000;  // give up if the hand never leaves
  double reject_show_ms = 1500;
  double dispatch_timeout_ms = 30000;
};

struct SelectorInput {
  double t_ms = 0;
  int hover_pocket = -1;        // pocket under the (smoothed) fingertip, -1 = none
  bool target_occluded = true;  // a hand/arm overlaps the current target pocket
  Prediction target_pred;       // classifier output for the target this frame
  bool robot_busy = false;
};

struct SelectorEvent {
  bool dispatch = false;  // send a pick request this frame
  int pocket = -1;
  Obj obj = Obj::Unknown;
};

class Selector {
 public:
  explicit Selector(const SelectorConfig& cfg = {}) : cfg_(cfg) {}

  SelectorEvent update(const SelectorInput& in);

  SelState state() const { return state_; }
  int target() const { return target_; }
  float progress() const { return progress_; }  // 0..1 while Dwelling
  const std::string& message() const { return msg_; }

 private:
  void go(SelState s, double t, const std::string& msg = "");
  void finish(SelState s, double t, const std::string& msg);

  SelectorConfig cfg_;
  SelState state_ = SelState::Idle;
  double t_enter_ = 0;
  int target_ = -1;
  int locked_ = -1;  // pocket that must be left before it can trigger again
  float progress_ = 0;
  int clear_count_ = 0;
  std::deque<Obj> votes_;
  bool saw_busy_ = false;
  std::string msg_;
};
