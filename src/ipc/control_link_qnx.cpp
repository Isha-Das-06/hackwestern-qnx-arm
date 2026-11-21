// control_link_qnx.cpp — QNX native message passing to the control task.
//
// UNTESTED until it runs on the Pi: written against the QNX 8 neutrino API
// (name_open / MsgSend), compiles only on QNX.
#include <errno.h>
#include <sys/dispatch.h>
#include <sys/neutrino.h>

#include <cstdio>
#include <cstring>

#include "control_link.hpp"

namespace {

class QnxLink : public ControlLink {
 public:
  ~QnxLink() override {
    if (coid_ != -1) name_close(coid_);
  }

  bool send_pick(const PickRequestMsg& req, PickReplyMsg& reply) override {
    if (!connect()) return false;
    if (MsgSend(coid_, &req, sizeof req, &reply, sizeof reply) == -1)
      return fail("MsgSend(pick)");
    return true;
  }

  bool status(PickReplyMsg& reply) override {
    if (!connect()) return false;
    PickStatusMsg m;
    if (MsgSend(coid_, &m, sizeof m, &reply, sizeof reply) == -1)
      return fail("MsgSend(status)");
    return true;
  }

  std::string describe() const override {
    return coid_ == -1 ? "qnx: " PICK_SERVICE_NAME " (not connected)"
                       : "qnx: " PICK_SERVICE_NAME;
  }

 private:
  // Connect lazily so the vision side can start before the control task and
  // reconnect if the control task restarts.
  bool connect() {
    if (coid_ != -1) return true;
    coid_ = name_open(PICK_SERVICE_NAME, 0);
    return coid_ != -1;
  }
  bool fail(const char* what) {
    fprintf(stderr, "warn: %s: %s\n", what, strerror(errno));
    name_close(coid_);
    coid_ = -1;
    return false;
  }
  int coid_ = -1;
};

}  // namespace

std::unique_ptr<ControlLink> ControlLink::create() {
  return std::make_unique<QnxLink>();
}
