// pick_protocol.hpp — wire format between the vision process and the C++
// control task. Shared by both sides; plain POD so it can go straight through
// QNX MsgSend()/MsgReply() with no serialisation.
//
//   vision (normal priority)  --PICK_MSG_REQUEST-->  control task (high prio)
//                             <--PickReplyMsg-------
//   vision polls              --PICK_MSG_STATUS--->  (returns current state)
//
// Message types start above _IO_MAX (0x1FF) so a name_attach() server can tell
// them apart from the resource-manager messages the kernel may send it.
#pragma once
#include <cstdint>

#define PICK_SERVICE_NAME "pickplace_ctrl"

enum : uint16_t {
  PICK_MSG_REQUEST = 0x0300,
  PICK_MSG_STATUS = 0x0301,
};

enum PickObj : uint8_t { PICK_OBJ_EGG = 1, PICK_OBJ_CUP = 2, PICK_OBJ_BLOCK = 3 };

enum PickState : int32_t {
  PICK_IDLE = 0,
  PICK_BUSY = 1,     // moving / gripping / lifting
  PICK_FAULT = 2,    // stopped on a grip fault (e.g. one jaw hit early)
  PICK_REJECTED = -1 // request refused (busy, bad pocket, ...)
};

struct PickRequestMsg {
  uint16_t type = PICK_MSG_REQUEST;
  uint16_t subtype = 0;
  uint32_t seq = 0;
  uint8_t pocket = 0;     // 0-based pocket index
  uint8_t obj = 0;        // PickObj
  uint16_t grip_min = 0;  // target pressure window, raw sensor units
  uint16_t grip_max = 0;
  uint16_t reserved = 0;
  uint64_t t_vision_ns = 0;  // CLOCK_MONOTONIC when the selection fired
};

struct PickStatusMsg {
  uint16_t type = PICK_MSG_STATUS;
  uint16_t subtype = 0;
};

struct PickReplyMsg {
  int32_t state = PICK_IDLE;  // PickState
  uint32_t seq = 0;           // seq of the request being worked on
  uint32_t fault_latency_us = 0;  // last fault: sensor event -> motor stop
};
