#include "selector.hpp"

#include <algorithm>

const char* sel_state_name(SelState s) {
  switch (s) {
    case SelState::Idle: return "IDLE";
    case SelState::Dwelling: return "DWELLING";
    case SelState::AwaitClear: return "AWAIT_CLEAR";
    case SelState::Classifying: return "CLASSIFYING";
    case SelState::Dispatched: return "DISPATCHED";
    case SelState::Rejected: return "REJECTED";
  }
  return "?";
}

void Selector::go(SelState s, double t, const std::string& msg) {
  state_ = s;
  t_enter_ = t;
  msg_ = msg;
}

// Back to Idle; the pocket just used stays locked until the finger leaves it.
void Selector::finish(SelState s, double t, const std::string& msg) {
  locked_ = target_;
  target_ = -1;
  progress_ = 0;
  go(s, t, msg);
}

SelectorEvent Selector::update(const SelectorInput& in) {
  SelectorEvent ev;
  const double t = in.t_ms;
  if (in.hover_pocket != locked_) locked_ = -1;  // finger left: unlock

  switch (state_) {
    case SelState::Idle:
      progress_ = 0;
      if (in.hover_pocket >= 0 && in.hover_pocket != locked_) {
        if (in.robot_busy) {
          msg_ = "robot busy";
          break;
        }
        target_ = in.hover_pocket;
        go(SelState::Dwelling, t, "hold...");
      }
      break;

    case SelState::Dwelling:
      if (in.hover_pocket != target_) {  // moved off or to another pocket
        target_ = -1;
        progress_ = 0;
        go(SelState::Idle, t, "");
        break;
      }
      progress_ = (float)std::min(1.0, (t - t_enter_) / cfg_.dwell_ms);
      if (progress_ >= 1.f) {
        clear_count_ = 0;
        go(SelState::AwaitClear, t, "selected - move hand away");
      }
      break;

    case SelState::AwaitClear:
      clear_count_ = in.target_occluded ? 0 : clear_count_ + 1;
      if (clear_count_ >= cfg_.clear_frames) {
        votes_.clear();
        go(SelState::Classifying, t, "identifying...");
      } else if (t - t_enter_ > cfg_.await_timeout_ms) {
        finish(SelState::Idle, t, "timed out waiting for hand to clear");
      }
      break;

    case SelState::Classifying: {
      if (in.target_occluded) {  // hand came back: wait again
        clear_count_ = 0;
        go(SelState::AwaitClear, t, "hand over pocket");
        break;
      }
      votes_.push_back(in.target_pred.cls);
      if ((int)votes_.size() < cfg_.vote_frames) break;
      int n[5] = {0};
      for (Obj o : votes_) n[(int)o]++;
      int best = 0;
      for (int i = 1; i < 5; ++i)
        if (n[i] > n[best]) best = i;
      Obj voted = (Obj)best;
      // Require a real majority, not just a plurality.
      if (n[best] * 2 <= (int)votes_.size()) voted = Obj::Unknown;

      if (voted == Obj::Empty) {
        go(SelState::Rejected, t, "pocket is empty");
      } else if (voted == Obj::Unknown) {
        go(SelState::Rejected, t, "can't identify object");
      } else {
        ev.dispatch = true;
        ev.pocket = target_;
        ev.obj = voted;
        saw_busy_ = false;
        go(SelState::Dispatched, t, std::string("picking ") + obj_name(voted));
      }
      break;
    }

    case SelState::Dispatched:
      if (in.robot_busy) saw_busy_ = true;
      // Done once the robot went busy and came back to idle (or never went
      // busy within 1 s, i.e. the request was dropped).
      if ((saw_busy_ && !in.robot_busy) || (!saw_busy_ && t - t_enter_ > 1000) ||
          t - t_enter_ > cfg_.dispatch_timeout_ms)
        finish(SelState::Idle, t, saw_busy_ ? "done" : "robot did not respond");
      break;

    case SelState::Rejected:
      if (t - t_enter_ > cfg_.reject_show_ms) finish(SelState::Idle, t, msg_);
      break;
  }
  return ev;
}
