"""Browser console for the app (needed on QNX: OpenCV there has no window support).

Open http://<pi-address>:8080 on any laptop/phone on the same network.
The page itself lives in python/web/ (index.html, app.css, app.js, fonts/).

Endpoints:
  /            the console page (and its static files)
  /stream      live camera, MJPEG (clean picture: the page draws the boxes)
  /state       everything the page shows, as JSON (polled a few times a second)
  /key?k=c     same as pressing a key in the window (c b tab 1 2 3 x m)
  /rect?x0=..  a box drawn with the mouse/finger (0..1 coordinates)
  /cmd?c=..    focus&i=N (pick box N for teaching) | cancel (cancel the move) | start (START)
               redraw&i=N (draw box N again) | teach&k=1..3 (teach from the non-empty box)
               forget&k=1..3 (delete one object's examples) | forgetbg (delete the empty-tray photo)

Uses only the Python standard library.
"""
import collections
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".woff2": "font/woff2",
         ".svg": "image/svg+xml", ".txt": "text/plain; charset=utf-8"}


class _Tee:
    """Copies everything printed into a small buffer the page can show."""

    def __init__(self, stream, lines):
        self.stream, self.lines, self.partial = stream, lines, ""

    def write(self, s):
        self.stream.write(s)
        self.partial += s
        while "\n" in self.partial:
            line, self.partial = self.partial.split("\n", 1)
            if line.strip() and not line.startswith(("[stat]", "[sel]")):
                self.lines.append(line)
        return len(s)

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


class WebUI:
    def __init__(self, port):
        self.port = port
        self.cv = threading.Condition()
        self.jpeg = None
        self.seq = 0
        self.state = {}
        self.state_lock = threading.Lock()
        self.events = collections.deque()
        self.lines = collections.deque(maxlen=12)
        sys.stdout = _Tee(sys.stdout, self.lines)
        ui = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # keep the terminal quiet
                pass

            def _send(self, body, ctype, cache=False):
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:  # browser closed the page mid-request: nothing to do
                    pass

            def _static(self, rel):
                path = os.path.realpath(os.path.join(WEB_DIR, rel.lstrip("/")))
                ext = os.path.splitext(path)[1].lower()
                if (not path.startswith(os.path.realpath(WEB_DIR) + os.sep)
                        or ext not in TYPES or not os.path.isfile(path)):
                    self.send_error(404)
                    return
                with open(path, "rb") as f:
                    self._send(f.read(), TYPES[ext], cache=ext == ".woff2")

            def do_GET(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                if u.path == "/":
                    self._static("index.html")
                elif u.path == "/state":
                    with ui.state_lock:
                        st = dict(ui.state)
                    st["log"] = list(ui.lines)
                    self._send(json.dumps(st).encode(), "application/json")
                elif u.path == "/key":
                    ui.events.append(("key", q.get("k", [""])[0]))
                    self._send(b"ok", "text/plain")
                elif u.path == "/cmd":
                    c = q.get("c", [""])[0]
                    if c == "focus":
                        try:
                            ui.events.append(("focus", int(q.get("i", ["0"])[0])))
                        except ValueError:
                            pass
                    elif c == "cancel":
                        ui.events.append(("cancel",))
                    elif c == "start":  # same as the green START button on the robot
                        ui.events.append(("start",))
                    elif c == "redraw":  # draw just one box again
                        try:
                            ui.events.append(("redraw", int(q.get("i", ["0"])[0])))
                        except ValueError:
                            pass
                    elif c in ("forget", "forgetbg"):  # forget one object (k=1..3) / the empty photo
                        k = q.get("k", [""])[0]
                        if c == "forgetbg":
                            ui.events.append(("forgetbg",))
                        elif k in ("1", "2", "3"):
                            ui.events.append(("forget", int(k)))
                    elif c == "teach":   # 1 egg / 2 cup / 3 block, from whichever box has something in it
                        k = q.get("k", [""])[0]
                        if k in ("1", "2", "3"):
                            ui.events.append(("teach", int(k)))
                    self._send(b"ok", "text/plain")
                elif u.path == "/rect":
                    try:
                        r = tuple(float(q[n][0]) for n in ("x0", "y0", "x1", "y1"))
                        ui.events.append(("rect",) + r)
                    except (KeyError, ValueError):
                        pass
                    self._send(b"ok", "text/plain")
                elif u.path == "/log":
                    self._send(json.dumps(list(ui.lines)).encode(), "application/json")
                elif u.path == "/stream":
                    self.send_response(200)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    last = -1
                    try:
                        while True:
                            with ui.cv:
                                ui.cv.wait_for(lambda: ui.seq != last, timeout=5)
                                if ui.seq == last or ui.jpeg is None:
                                    continue
                                last, jpg = ui.seq, ui.jpeg
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                             + f"Content-Length: {len(jpg)}\r\n\r\n".encode() + jpg + b"\r\n")
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                else:
                    self._static(u.path)

        self.server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def publish(self, jpeg_bytes):
        with self.cv:
            self.jpeg = jpeg_bytes
            self.seq += 1
            self.cv.notify_all()

    def set_state(self, state):
        with self.state_lock:
            self.state = state

    def pop_events(self):
        out = []
        while self.events:
            out.append(self.events.popleft())
        return out
