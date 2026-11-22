// main.cpp — pickvision: point-and-dwell pocket selection + object ID.
//
// Threads (same layout as the workshop's handtrack_node):
//   camera thread  -> newest-wins frame slot (never queues stale frames)
//   main thread    -> hand tracking, pointing, selection, classification, UI
//
// The vision process never touches the motors. It sends ONE PickRequestMsg to
// the control task when a selection is confirmed; the control task (higher
// priority, on QNX) owns grip/lift/stop. That is why a busy or slow vision
// loop cannot delay a grip fault stop.
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <opencv2/imgcodecs.hpp>
#include "vision/cv_compat.hpp"
#include <string>
#include <thread>

#ifdef PV_GUI
#include <opencv2/highgui.hpp>
#endif

#include "app/classifier.hpp"
#include "app/pointer.hpp"
#include "app/selector.hpp"
#include "app/tray.hpp"
#include "ipc/control_link.hpp"
#include "platform/frame_source.hpp"
#include "vision/handtracking.hpp"

namespace {

#ifdef PV_QNX
constexpr bool DEFAULT_FLIP = false;  // C270 looks down at the tray
#else
constexpr bool DEFAULT_FLIP = true;   // laptop selfie cam: mirror like a mirror
#endif

double now_ms() {
  using namespace std::chrono;
  return duration<double, std::milli>(steady_clock::now().time_since_epoch())
      .count();
}
uint64_t now_ns() {
  using namespace std::chrono;
  return (uint64_t)duration_cast<nanoseconds>(
             steady_clock::now().time_since_epoch())
      .count();
}

// ---------------------------------------------------------------- arguments
struct Args {
  CameraConfig cam;
  std::string models = "models";
  std::string config = "config";
  bool flip = DEFAULT_FLIP;
  bool headless = false;
  int frames = 0;  // >0: process this many frames, print stats, exit
  std::string save_frame;  // write the last annotated frame here
  int max_hands = 2;
  int threads = 3;
  bool point_check = true;  // only a pointing hand selects
};

void usage() {
  printf(
      "pickvision [options]\n"
      "  --cam N          webcam index (laptop) / camapi unit (QNX, default 5)\n"
      "  --size WxH       requested capture size (default 1280x720)\n"
      "  --file PATH      use an image or video instead of a camera\n"
      "  --models DIR     .tflite directory (default models)\n"
      "  --config DIR     tray/classifier/grip config (default config)\n"
      "  --flip/--no-flip mirror the image (default: on for laptop)\n"
      "  --headless       no window; print status once a second\n"
      "  --frames N       process N frames then exit (self-test)\n"
      "  --save-frame P   save the last annotated frame to P\n"
      "  --hands N        max hands to track (default 2)\n"
      "  --threads N      inference threads (default 3)\n"
      "  --no-point-check any hand over a pocket selects (old behaviour)\n");
}

bool parse(int argc, char** argv, Args& a) {
  for (int i = 1; i < argc; ++i) {
    std::string s = argv[i];
    auto next = [&](const char* name) -> const char* {
      if (i + 1 >= argc) {
        fprintf(stderr, "error: %s needs a value\n", name);
        exit(2);
      }
      return argv[++i];
    };
    if (s == "--cam") a.cam.unit = atoi(next("--cam"));
    else if (s == "--size") {
      if (sscanf(next("--size"), "%dx%d", &a.cam.width, &a.cam.height) != 2) return false;
    } else if (s == "--file") a.cam.file = next("--file");
    else if (s == "--models") a.models = next("--models");
    else if (s == "--config") a.config = next("--config");
    else if (s == "--flip") a.flip = true;
    else if (s == "--no-flip") a.flip = false;
    else if (s == "--headless") a.headless = true;
    else if (s == "--frames") a.frames = atoi(next("--frames"));
    else if (s == "--save-frame") a.save_frame = next("--save-frame");
    else if (s == "--hands") a.max_hands = std::max(1, atoi(next("--hands")));
    else if (s == "--threads") a.threads = atoi(next("--threads"));
    else if (s == "--no-point-check") a.point_check = false;
    else if (s == "-h" || s == "--help") { usage(); exit(0); }
    else { fprintf(stderr, "unknown option %s\n", s.c_str()); return false; }
  }
#ifndef PV_GUI
  a.headless = true;
#endif
  return true;
}

// ---------------------------------------------------------------- grip table
// Pressure window per object, raw sensor units from the grip tests.
struct GripTable {
  uint16_t lo[4] = {0, 80, 150, 300};
  uint16_t hi[4] = {0, 140, 260, 600};
  void load(const std::string& path) {
    cv::FileStorage fs(path, cv::FileStorage::READ);
    if (!fs.isOpened()) {
      fprintf(stderr, "warn: %s missing, using placeholder grip values\n",
              path.c_str());
      return;
    }
    const char* keys[4] = {"", "egg", "cup", "block"};
    for (int i = 1; i < 4; ++i) {
      std::vector<int> v;
      fs[keys[i]] >> v;
      if (v.size() == 2) lo[i] = (uint16_t)v[0], hi[i] = (uint16_t)v[1];
    }
  }
};

// ---------------------------------------------------------------- geometry
// Does this hand (or its forearm) cover the rectangle? From a top-down camera
// the arm hides the pocket too, so a corridor from the wrist back along the
// forearm is tested as well as the hand box.
bool hand_covers(const Hand& h, const cv::Rect& r, cv::Size frame) {
  if ((hand_bbox(h, frame) & r).area() > 0) return true;
  cv::Point2f wrist = h.pts[lm::WRIST], mcp = h.pts[lm::MIDDLE_MCP];
  cv::Point2f dir = wrist - mcp;
  float palm = std::hypot(dir.x, dir.y);
  if (palm < 1.f) return false;
  dir *= 1.f / palm;
  cv::Rect grown(r.x - (int)(palm * 0.5f), r.y - (int)(palm * 0.5f),
                 r.width + (int)palm, r.height + (int)palm);
  for (float k = 0.f; k <= 4.f; k += 0.25f) {
    cv::Point2f p = wrist + dir * (k * palm);
    if (grown.contains(cv::Point(cvRound(p.x), cvRound(p.y)))) return true;
  }
  return false;
}

// ---------------------------------------------------------------- drawing
const int HAND_EDGES[][2] = {{0, 1},   {1, 2},   {2, 3},   {3, 4},   {0, 5},
                             {5, 6},   {6, 7},   {7, 8},   {5, 9},   {9, 10},
                             {10, 11}, {11, 12}, {9, 13},  {13, 14}, {14, 15},
                             {15, 16}, {13, 17}, {17, 18}, {18, 19}, {19, 20},
                             {0, 17}};

void text(cv::Mat& img, const std::string& s, cv::Point p, double scale,
          cv::Scalar col, int thick = 1) {
  cv::putText(img, s, p, cv::FONT_HERSHEY_SIMPLEX, scale, {0, 0, 0}, thick + 3,
              cv::LINE_AA);
  cv::putText(img, s, p, cv::FONT_HERSHEY_SIMPLEX, scale, col, thick,
              cv::LINE_AA);
}

void draw_hand(cv::Mat& img, const Hand& h, bool primary) {
  cv::Scalar c = primary ? cv::Scalar(0, 255, 0) : cv::Scalar(160, 160, 160);
  for (auto& e : HAND_EDGES)
    cv::line(img, h.pts[e[0]], h.pts[e[1]], c, 2, cv::LINE_AA);
  for (auto& p : h.pts) cv::circle(img, p, 3, {255, 255, 255}, -1, cv::LINE_AA);
}

// ---------------------------------------------------------------- UI state
struct Ui {
  Tray* tray = nullptr;
  std::string tray_path;
  cv::Size frame{0, 0};
  bool calibrating = false;
  int calib_idx = 0;
  bool dragging = false;
  cv::Point drag0, drag1;
  int focus = 0;
  bool show_mask = false;
  bool help = true;
};

#ifdef PV_GUI
void on_mouse(int ev, int x, int y, int, void* ud) {
  Ui& ui = *static_cast<Ui*>(ud);
  if (!ui.calibrating || ui.frame.width == 0) return;
  if (ev == cv::EVENT_LBUTTONDOWN) {
    ui.dragging = true;
    ui.drag0 = ui.drag1 = {x, y};
  } else if (ev == cv::EVENT_MOUSEMOVE && ui.dragging) {
    ui.drag1 = {x, y};
  } else if (ev == cv::EVENT_LBUTTONUP && ui.dragging) {
    ui.dragging = false;
    cv::Rect r(ui.drag0, cv::Point(x, y));
    if (r.width > 10 && r.height > 10) {
      ui.tray->set_pocket(ui.calib_idx,
                          {(float)r.x / ui.frame.width, (float)r.y / ui.frame.height,
                           (float)r.width / ui.frame.width,
                           (float)r.height / ui.frame.height});
      if (++ui.calib_idx >= ui.tray->size()) {
        ui.calibrating = false;
        ui.tray->save(ui.tray_path);
        printf("tray saved to %s\n", ui.tray_path.c_str());
      }
    }
  }
}
#endif

}  // namespace

int main(int argc, char** argv) {
  Args args;
  if (!parse(argc, argv, args)) {
    usage();
    return 2;
  }

  // ---- config ----
  const std::string tray_path = args.config + "/tray.yml";
  const std::string clf_path = args.config + "/classifier.yml";
  Tray tray;
  if (!tray.load(tray_path))
    printf("no %s yet: using default pocket layout (press c to calibrate)\n",
           tray_path.c_str());
  PocketClassifier clf;
  if (clf.load(clf_path))
    printf("classifier: %d egg / %d cup / %d block samples\n",
           clf.num_samples(Obj::Egg), clf.num_samples(Obj::Cup),
           clf.num_samples(Obj::Block));
  GripTable grip;
  grip.load(args.config + "/grip.yml");

  // ---- models ----
  HandTrackConfig hcfg;
  hcfg.det_model = args.models + "/palm_detection_lite.tflite";
  hcfg.lm_model = args.models + "/hand_landmark_lite.tflite";
  hcfg.mirror = args.flip;
  hcfg.threads = args.threads;
  HandTrack tracker(hcfg);
  if (!tracker.ok()) return 1;

  auto link = ControlLink::create();

  // ---- camera -> newest-wins slot ----
  std::mutex mx;
  std::condition_variable cv_frame;
  cv::Mat slot;
  uint64_t slot_seq = 0;
  std::atomic<uint64_t> cam_frames{0};
  auto cam = FrameSource::create(args.cam);
  if (!cam->start([&](const cv::Mat& f) {
        {
          std::lock_guard<std::mutex> lk(mx);
          f.copyTo(slot);
          ++slot_seq;
        }
        ++cam_frames;
        cv_frame.notify_one();
      }))
    return 1;

  printf("pickvision: camera=%s backend=%s link=%s flip=%d\n",
         cam->describe().c_str(), tracker.backend().c_str(),
         link->describe().c_str(), (int)args.flip);

  Ui ui;
  ui.tray = &tray;
  ui.tray_path = tray_path;
#ifdef PV_GUI
  const char* WIN = "pickvision";
  if (!args.headless) {
    cv::namedWindow(WIN, cv::WINDOW_NORMAL);
    cv::resizeWindow(WIN, 1280, 720);
    cv::setMouseCallback(WIN, on_mouse, &ui);
  }
#endif

  PointerTracker pointer;
  Selector selector;
  std::vector<Prediction> last_pred(tray.size());
  std::vector<bool> occluded(tray.size(), false);
  uint32_t seq = 0;
  PickReplyMsg robot;
  double t_status = 0;
  bool link_ok = true;
  SelState prev_state = SelState::Idle;

  // stats
  double t_stat = now_ms();
  int n_proc = 0, n_stat = 0;
  uint64_t cam_at_stat = 0;
  double det_sum = 0, lm_sum = 0, total_sum = 0;
  int det_runs = 0, hands_seen = 0;
  float fps_cam = 0, fps_inf = 0;
  uint64_t last_seq = 0;
  cv::Mat frame, view;

  for (;;) {
    {
      std::unique_lock<std::mutex> lk(mx);
      if (!cv_frame.wait_for(lk, std::chrono::seconds(3),
                             [&] { return slot_seq != last_seq; })) {
        fprintf(stderr, "error: no frames from camera for 3 s\n");
        break;
      }
      last_seq = slot_seq;
      slot.copyTo(frame);
    }
    const double t0 = now_ms();
    if (args.flip) cv::flip(frame, frame, 1);
    ui.frame = frame.size();

    // ---- hands ----
    std::vector<Hand> hands = tracker.detect(frame, args.max_hands);
    const Hand* primary = nullptr;
    int best_area = -1;
    for (const auto& h : hands) {
      int a = hand_bbox(h, frame.size()).area();
      if (a > best_area) best_area = a, primary = &h;
    }
    PointerState ps = pointer.update(primary, t0);
    // Fingertip over a pocket; it only counts as a selection when the hand is
    // in a pointing shape, so placing/shuffling objects can't trigger a pick.
    int over = ps.valid ? tray.hit(ps.tip, frame.size()) : -1;
    int hover = (ps.pointing || !args.point_check) ? over : -1;

    // ---- pockets: occlusion + classification ----
    for (int i = 0; i < tray.size(); ++i) {
      cv::Rect r = tray.rect_px(i, frame.size());
      occluded[i] = false;
      for (const auto& h : hands)
        if (hand_covers(h, r, frame.size())) occluded[i] = true;
      if (!occluded[i] && r.area() > 0) last_pred[i] = clf.predict(i, frame(r));
    }

    // ---- robot status (cheap, ~10 Hz) ----
    if (t0 - t_status > 100) {
      t_status = t0;
      link_ok = link->status(robot);
    }
    const bool robot_busy = link_ok && robot.state == PICK_BUSY;

    // ---- selection ----
    SelectorInput si;
    si.t_ms = t0;
    si.hover_pocket = hover;
    int tgt = selector.target();
    si.target_occluded = tgt >= 0 ? (bool)occluded[tgt] : true;
    si.target_pred = tgt >= 0 ? last_pred[tgt] : Prediction{};
    si.robot_busy = robot_busy;
    SelectorEvent ev = selector.update(si);

    if (selector.state() != prev_state) {
      printf("[sel] %s -> %s  pocket=%d  %s\n", sel_state_name(prev_state),
             sel_state_name(selector.state()), selector.target() + 1,
             selector.message().c_str());
      prev_state = selector.state();
    }
    if (ev.dispatch) {
      PickRequestMsg req;
      req.seq = ++seq;
      req.pocket = (uint8_t)ev.pocket;
      req.obj = (uint8_t)ev.obj;
      req.grip_min = grip.lo[(int)ev.obj];
      req.grip_max = grip.hi[(int)ev.obj];
      req.t_vision_ns = now_ns();
      PickReplyMsg rep;
      if (!link->send_pick(req, rep))
        printf("[pick] control task unreachable (%s)\n", link->describe().c_str());
      else
        printf("[pick] seq=%u pocket=%d obj=%s grip=[%u,%u] -> state=%d\n",
               req.seq, ev.pocket + 1, obj_name(ev.obj), req.grip_min,
               req.grip_max, rep.state);
      fflush(stdout);
      t_status = 0;  // refresh robot state on the next frame
    }

    const double t_proc = now_ms() - t0;

    // ---- stats ----
    ++n_proc, ++n_stat;
    total_sum += t_proc;
    lm_sum += tracker.last_lm_ms;
    if (tracker.ran_detector) det_sum += tracker.last_det_ms, ++det_runs;
    if (!hands.empty()) ++hands_seen;
    if (t0 - t_stat >= 1000) {
      double dt = (t0 - t_stat) / 1000.0;
      fps_inf = (float)(n_stat / dt);
      fps_cam = (float)((cam_frames - cam_at_stat) / dt);
      if (args.headless)
        printf("[stat] cam %.1f fps | proc %.1f fps | hands %zu | hover P%d | "
               "pointing %s (bend I%.0f M%.0f R%.0f, 3d=%d) | %s\n",
               fps_cam, fps_inf, hands.size(), hover + 1,
               ps.pointing ? "YES" : "no",
               primary ? finger_bends(*primary)[0] : 0.f,
               primary ? finger_bends(*primary)[1] : 0.f,
               primary ? finger_bends(*primary)[2] : 0.f,
               primary ? (int)primary->has_world : -1,
               sel_state_name(selector.state()));
      t_stat = t0;
      n_stat = 0;
      cam_at_stat = cam_frames;
    }

    // ---- draw ----
    const bool want_view = !args.headless || !args.save_frame.empty();
    if (want_view) {
      view = frame.clone();
      for (int i = 0; i < tray.size(); ++i) {
        cv::Rect r = tray.rect_px(i, frame.size());
        cv::Scalar col(140, 140, 140);
        int th = 2;
        if (i == hover) col = {0, 220, 255}, th = 3;
        if (i == selector.target()) col = {255, 200, 0}, th = 4;
        if (ui.calibrating && i == ui.calib_idx) col = {255, 0, 255};
        cv::rectangle(view, r, col, th);
        if (i == ui.focus && !ui.calibrating)
          cv::rectangle(view, r + cv::Point(-4, -4) + cv::Size(8, 8),
                        {255, 255, 255}, 1);
        const Prediction& p = last_pred[i];
        char buf[96];
        snprintf(buf, sizeof buf, "%s %s %.0f%%%s", tray.pocket(i).name.c_str(),
                 obj_name(p.cls), p.conf * 100, occluded[i] ? " (hand)" : "");
        text(view, buf, {r.x + 4, r.y + 20}, 0.55, col, 1);
        if (ui.show_mask && r.area() > 0 && !occluded[i]) {
          cv::Mat m;
          clf.predict(i, frame(r), &m);
          cv::resize(m, m, r.size(), 0, 0, cv::INTER_NEAREST);
          cv::Mat roi = view(r);
          roi.setTo(cv::Scalar(255, 0, 255), m);
        }
      }
      for (const auto& h : hands) draw_hand(view, h, &h == primary);
      if (ps.valid) {
        cv::Scalar pc = hover >= 0 ? cv::Scalar(0, 220, 255) : cv::Scalar(200, 200, 200);
        cv::circle(view, ps.tip, 8, pc, 2, cv::LINE_AA);
        if (over >= 0 && hover < 0)
          text(view, "point with index finger",
               {cvRound(ps.tip.x) + 14, cvRound(ps.tip.y) - 12}, 0.6,
               {200, 200, 200}, 1);
        if (selector.state() == SelState::Dwelling)
          cv::ellipse(view, ps.tip, {26, 26}, -90, 0,
                      360 * selector.progress(), {255, 200, 0}, 4, cv::LINE_AA);
      }
      if (ui.calibrating && ui.dragging)
        cv::rectangle(view, cv::Rect(ui.drag0, ui.drag1), {255, 0, 255}, 2);

      char buf[256];
      snprintf(buf, sizeof buf, "%s  %s", sel_state_name(selector.state()),
               selector.message().c_str());
      text(view, buf, {12, 32}, 0.8, {255, 255, 255}, 2);
      snprintf(buf, sizeof buf,
               "cam %.0f fps | proc %.0f fps %.0f ms (det %.0f lm %.0f) | hover P%d | pointing %s (bend I%.0f M%.0f R%.0f) | robot %s | %s",
               fps_cam, fps_inf, t_proc, tracker.ran_detector ? tracker.last_det_ms : 0.0,
               tracker.last_lm_ms, hover + 1, ps.pointing ? "YES" : "no",
               primary ? finger_bends(*primary)[0] : 0.f,
               primary ? finger_bends(*primary)[1] : 0.f,
               primary ? finger_bends(*primary)[2] : 0.f,
               !link_ok ? "offline" : robot.state == PICK_BUSY ? "BUSY"
                          : robot.state == PICK_FAULT          ? "FAULT"
                                                               : "idle",
               tracker.backend().c_str());
      text(view, buf, {12, 58}, 0.5, {220, 220, 220}, 1);
      if (ui.calibrating) {
        snprintf(buf, sizeof buf, "CALIBRATE: drag a box around pocket %d of %d",
                 ui.calib_idx + 1, tray.size());
        text(view, buf, {12, 86}, 0.7, {255, 0, 255}, 2);
      } else if (ui.help) {
        snprintf(buf, sizeof buf,
                 "samples egg %d cup %d block %d | focus P%d",
                 clf.num_samples(Obj::Egg), clf.num_samples(Obj::Cup),
                 clf.num_samples(Obj::Block), ui.focus + 1);
        text(view, buf, {12, 86}, 0.5, {200, 255, 200}, 1);
        text(view,
             "q quit | c calibrate | b empty-tray bg | TAB focus | 1 egg 2 cup 3 block | x clear | m mask | h help",
             {12, view.rows - 14}, 0.5, {200, 200, 200}, 1);
      }
    }

#ifdef PV_GUI
    if (!args.headless) {
      cv::imshow(WIN, view);
      int key = cv::waitKey(1);
      if (key == 'q' || key == 27) break;
      if (key == 'h') ui.help = !ui.help;
      if (key == 'm') ui.show_mask = !ui.show_mask;
      if (key == 'c') {
        ui.calibrating = !ui.calibrating;
        ui.calib_idx = 0;
      }
      if (key == 9) ui.focus = (ui.focus + 1) % tray.size();
      if (key == 'b') {
        if (!hands.empty()) {
          printf("move your hand out of view before capturing the empty tray\n");
        } else {
          for (int i = 0; i < tray.size(); ++i)
            clf.set_background(i, frame(tray.rect_px(i, frame.size())));
          clf.save(clf_path);
          printf("empty-tray backgrounds captured for %d pockets\n", tray.size());
        }
      }
      if (key >= '1' && key <= '3') {
        if (occluded[ui.focus]) {
          printf("hand is over P%d - move it away first\n", ui.focus + 1);
        } else {
          clf.add_sample((Obj)(key - '0'), ui.focus,
                         frame(tray.rect_px(ui.focus, frame.size())));
          clf.save(clf_path);
        }
      }
      if (key == 'x') {
        clf.clear_samples();
        clf.save(clf_path);
        printf("samples cleared\n");
      }
    }
#endif

    if (args.frames > 0 && n_proc >= args.frames) break;
  }

  if (!args.save_frame.empty() && !view.empty()) cv::imwrite(args.save_frame, view);
  cam->stop();

  if (n_proc > 0)
    printf(
        "[summary] frames=%d  avg proc %.1f ms  avg lm %.1f ms  det runs %d "
        "(avg %.1f ms)  frames with hands %d\n",
        n_proc, total_sum / n_proc, lm_sum / n_proc, det_runs,
        det_runs ? det_sum / det_runs : 0.0, hands_seen);
  return 0;
}
