"""
Sends move history + health samples to the cloud dashboard (Vultr + Tiger Data).

The robot never waits on this: send() only appends to a list, and a background
thread posts batches over HTTPS. If the network is down, records are kept (and
saved to disk) and sent later, so the robot works fully offline.

Config: config/cloud.json  (not committed - holds the token)
    {"url": "http://<vultr-ip>", "token": "<same INGEST_TOKEN as the server>"}
No file -> cloud sync is off.

Timestamps: the Pi clock may be unset, so each record carries how many seconds
ago it happened ("age_s", from a monotonic clock); the server turns that into
real time on arrival.
"""

import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid

MAX_KEEP = 5000      # records kept while offline (oldest dropped first)
BATCH = 200          # records per request
PERIOD_S = 2.0       # how often to try sending
MAX_BACKOFF_S = 60.0


class CloudSync:
    def __init__(self, url, token, spool_path, device=None):
        self.url = url.rstrip("/") + "/api/ingest"
        self.token = token
        self.spool = spool_path
        self.device = device or socket.gethostname() or "pickvision"
        self.lock = threading.Lock()
        self.pending = []           # [{"kind": "move"|"health", "id", "mono", ...}]
        self.sent = 0
        self.last_ok = None         # monotonic time of the last good send
        self.last_err = ""
        self._load_spool()
        threading.Thread(target=self._run, daemon=True, name="cloud-sync").start()

    @classmethod
    def from_config(cls, cfg_path, spool_path):
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
        except FileNotFoundError:
            print("cloud: off (no config/cloud.json)")
            return None
        except (OSError, ValueError) as e:
            print(f"cloud: off (bad config/cloud.json: {e})")
            return None
        if not cfg.get("url") or not cfg.get("token"):
            print("cloud: off (config/cloud.json needs url and token)")
            return None
        print(f"cloud: sending history to {cfg['url']}")
        return cls(cfg["url"], cfg["token"], spool_path, cfg.get("device"))

    # ---------------------------------------------------------------- called by the app
    def send(self, kind, **fields):
        """Queue one record. Never blocks on the network."""
        rec = {"kind": kind, "id": uuid.uuid4().hex, "mono": time.monotonic(), **fields}
        with self.lock:
            self.pending.append(rec)
            if len(self.pending) > MAX_KEEP:
                del self.pending[: len(self.pending) - MAX_KEEP]

    def status(self):
        with self.lock:
            n = len(self.pending)
        return {"queued": n, "sent": self.sent, "error": self.last_err,
                "last_ok_s": None if self.last_ok is None else round(time.monotonic() - self.last_ok)}

    # ---------------------------------------------------------------- background thread
    def _run(self):
        backoff = PERIOD_S
        while True:
            time.sleep(backoff)
            with self.lock:
                batch = self.pending[:BATCH]
            if not batch:
                backoff = PERIOD_S
                continue
            try:
                self._post(batch)
            except Exception as e:  # network down, server down, bad token...
                msg = str(e)
                if msg != self.last_err:
                    print(f"cloud: can't send yet ({msg}) - keeping {len(self.pending)} records")
                self.last_err = msg
                self._save_spool()
                backoff = min(backoff * 2, MAX_BACKOFF_S)
                continue
            ids = {r["id"] for r in batch}
            with self.lock:
                self.pending = [r for r in self.pending if r["id"] not in ids]
                left = len(self.pending)
            if self.last_err:
                print("cloud: connected again")
            self.sent += len(batch)
            self.last_ok, self.last_err = time.monotonic(), ""
            if left == 0:
                self._save_spool()
            backoff = 0.2 if left else PERIOD_S  # more waiting -> send again soon

    def _post(self, batch):
        now = time.monotonic()
        recs = []
        for r in batch:
            out = {k: v for k, v in r.items() if k != "mono"}
            out["age_s"] = round(now - r["mono"], 3)
            recs.append(out)
        body = json.dumps({"device": self.device, "records": recs}).encode()
        req = urllib.request.Request(self.url, data=body, method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {self.token}"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"server said {e.code}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(str(e.reason)) from None

    # ---------------------------------------------------------------- offline spool
    def _save_spool(self):
        """Keep unsent records on disk so a restart while offline doesn't lose them."""
        now, wall = time.monotonic(), time.time()
        with self.lock:
            # store wall-clock-relative times; on reload they're turned back into mono
            rows = [{**{k: v for k, v in r.items() if k != "mono"}, "ago_s": now - r["mono"],
                     "saved": wall} for r in self.pending]
        try:
            tmp = self.spool + ".tmp"
            with open(tmp, "w") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")
            os.replace(tmp, self.spool)
        except OSError as e:
            print(f"cloud: couldn't save the offline queue: {e}")

    def _load_spool(self):
        try:
            with open(self.spool) as f:
                rows = [json.loads(line) for line in f if line.strip()]
        except (OSError, ValueError):
            return
        now, wall = time.monotonic(), time.time()
        for row in rows[-MAX_KEEP:]:
            # time passed since saving (0 if the clock looks wrong) + how old it was then
            gap = wall - row.pop("saved", wall)
            ago = row.pop("ago_s", 0) + (gap if 0 <= gap < 30 * 86400 else 0)
            row["mono"] = now - ago
            self.pending.append(row)
        if self.pending:
            print(f"cloud: {len(self.pending)} records from last time waiting to send")
