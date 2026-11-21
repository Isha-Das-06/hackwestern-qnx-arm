// control_link_sim.cpp — stand-in control task for laptop testing.
#include <chrono>
#include <cstdio>

#include "control_link.hpp"

namespace {

class SimLink : public ControlLink {
  using clock = std::chrono::steady_clock;

 public:
  bool send_pick(const PickRequestMsg& req, PickReplyMsg& reply) override {
    if (busy()) {
      reply.state = PICK_REJECTED;
      return true;
    }
    static const char* names[] = {"?", "egg", "cup", "block"};
    printf("[ctrl-sim] PICK seq=%u pocket=%u obj=%s grip=[%u,%u]\n", req.seq,
           req.pocket + 1, names[req.obj <= 3 ? req.obj : 0], req.grip_min,
           req.grip_max);
    fflush(stdout);
    seq_ = req.seq;
    until_ = clock::now() + std::chrono::seconds(3);
    reply.state = PICK_BUSY;
    reply.seq = seq_;
    return true;
  }

  bool status(PickReplyMsg& reply) override {
    reply.state = busy() ? PICK_BUSY : PICK_IDLE;
    reply.seq = seq_;
    return true;
  }

  std::string describe() const override { return "sim (no robot)"; }

 private:
  bool busy() const { return clock::now() < until_; }
  clock::time_point until_{};
  uint32_t seq_ = 0;
};

}  // namespace

std::unique_ptr<ControlLink> ControlLink::create() {
  return std::make_unique<SimLink>();
}
