// ctrl_stub_qnx.cpp — stand-in for the real control task, for testing the
// vision -> control path on the Pi before the motor code is ready.
//
// It registers PICK_SERVICE_NAME, prints each request, and reports BUSY for
// 3 s. The real control task keeps exactly this message loop and replaces the
// timer with the Pico conversation. UNTESTED until it runs on QNX.
//
// Run the real control task at a higher priority than vision, e.g.
//   on -p 50 ./ctrl_task     (vision stays at the default 10)
#include <errno.h>
#include <sys/dispatch.h>
#include <sys/iomsg.h>
#include <sys/neutrino.h>
#include <time.h>

#include <cstdio>
#include <cstring>

#include "ipc/pick_protocol.hpp"

static uint64_t now_ns() {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (uint64_t)t.tv_sec * 1000000000ull + t.tv_nsec;
}

int main() {
  name_attach_t* att = name_attach(nullptr, PICK_SERVICE_NAME, 0);
  if (!att) {
    perror("name_attach");
    return 1;
  }
  printf("ctrl_stub: listening as %s\n", PICK_SERVICE_NAME);

  union {
    struct _pulse pulse;
    uint16_t type;
    PickRequestMsg pick;
    PickStatusMsg status;
  } msg;
  PickReplyMsg state;
  uint64_t busy_until = 0;

  for (;;) {
    int rcvid = MsgReceive(att->chid, &msg, sizeof msg, nullptr);
    if (rcvid == -1) {
      perror("MsgReceive");
      break;
    }
    if (rcvid == 0) continue;  // pulse (e.g. client disconnect)
    if (msg.type == _IO_CONNECT) {  // name_open() handshake
      MsgReply(rcvid, EOK, nullptr, 0);
      continue;
    }
    if (msg.type > _IO_BASE && msg.type <= _IO_MAX) {
      MsgError(rcvid, ENOSYS);
      continue;
    }

    const uint64_t t = now_ns();
    state.state = t < busy_until ? PICK_BUSY : PICK_IDLE;

    if (msg.type == PICK_MSG_REQUEST) {
      if (state.state == PICK_BUSY) {
        PickReplyMsg r = state;
        r.state = PICK_REJECTED;
        MsgReply(rcvid, EOK, &r, sizeof r);
        continue;
      }
      printf("ctrl_stub: PICK seq=%u pocket=%u obj=%u grip=[%u,%u] "
             "vision->ctrl %.3f ms\n",
             msg.pick.seq, msg.pick.pocket + 1, msg.pick.obj,
             msg.pick.grip_min, msg.pick.grip_max,
             (t - msg.pick.t_vision_ns) / 1e6);
      busy_until = t + 3000000000ull;
      state.state = PICK_BUSY;
      state.seq = msg.pick.seq;
      MsgReply(rcvid, EOK, &state, sizeof state);
    } else if (msg.type == PICK_MSG_STATUS) {
      MsgReply(rcvid, EOK, &state, sizeof state);
    } else {
      MsgError(rcvid, ENOSYS);
    }
  }
  name_detach(att, 0);
  return 0;
}
