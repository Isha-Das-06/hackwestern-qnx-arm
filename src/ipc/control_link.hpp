// control_link.hpp — how the vision process talks to the control task.
//
//   laptop: control_link_sim.cpp  — logs the request and fakes a 3 s pick
//   QNX:    control_link_qnx.cpp  — name_open(PICK_SERVICE_NAME) + MsgSend()
#pragma once
#include <memory>
#include <string>

#include "pick_protocol.hpp"

class ControlLink {
 public:
  virtual ~ControlLink() = default;
  /// Send a pick request. Returns false if the control task is unreachable;
  /// reply.state says whether it was accepted.
  virtual bool send_pick(const PickRequestMsg& req, PickReplyMsg& reply) = 0;
  /// Current control task state (cheap; called a few times a second).
  virtual bool status(PickReplyMsg& reply) = 0;
  virtual std::string describe() const = 0;

  static std::unique_ptr<ControlLink> create();
};
