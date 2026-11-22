// PickVision operator console v2.
"use strict";
const $ = id => document.getElementById(id);
const cam = $("cam"), cv = $("overlay"), frameEl = $("frame");
// what the operator sees; the ids (egg/cup/block) stay the same inside the app and to the arm
const OBJ = { egg: "Pill bottle", cup: "Squeeze bottle", block: "Pills", empty: "Empty", unknown: "Unknown" };
// grip strength the arm uses for each (mks_servo/config/grip_profiles.json): hardcoded for now
const GRIP = { egg: "Medium", cup: "Firm", block: "Light" };
const KNOWN = ["egg", "cup", "block"];
const TEACH_GOAL = 5;
const HAND = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],
              [9,13],[13,14],[14,15],[15,16],[13,17],[17,18],[18,19],[19,20],[0,17]];
const C = { blue: "#3B82F6", amber: "#F5A524", green: "#22C55E", text: "#E9ECF0", line: "rgba(233,236,240,.42)" };
let S = null, online = false, fails = 0, drag = null, lastMoves = "", prevState = "", reject = null;
const hist = { fps: [] };

const send = (path) => fetch(path, { cache: "no-store" }).catch(() => {});
const key = (k) => send("/key?k=" + encodeURIComponent(k));
const cmd = (c, extra = "") => send(`/cmd?c=${c}${extra}`);
const upper = (s) => s ? s[0].toUpperCase() + s.slice(1) : s;
const objName = (id) => OBJ[id] || upper(id);              // "Pill bottle"
const objLower = (id) => objName(id).toLowerCase();         // "pill bottle" (inside a sentence)
const gripText = (id) => GRIP[id] ? `${GRIP[id].toLowerCase()} grip` : "";  // "medium grip"
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
// Pi times -> this computer's clock (the Pi's clock can be wrong after a reboot without internet)
const clock = (epoch) => new Date(S && S.sys && S.sys.now ? Date.now() - (S.sys.now - epoch) * 1000 : epoch * 1000)
  .toLocaleTimeString([], { hour12: false });
const busyMove = (st) => !["IDLE", "DISPATCHED", "REJECTED"].includes(st);

// ---------------------------------------------------------------- sound (Web Audio, nothing to download)
const Sound = {
  ctx: null, on: localStorage.getItem("pv-sound") === "1",
  LOUD: 4,  // master volume boost (1 = original quiet level)
  ensure() {
    if (!this.ctx) {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      // boost everything, with a limiter so overlapping beeps don't crackle
      const lim = this.ctx.createDynamicsCompressor();
      lim.threshold.value = -6; lim.knee.value = 0; lim.ratio.value = 20; lim.attack.value = .002; lim.release.value = .1;
      this.out = this.ctx.createGain(); this.out.gain.value = this.LOUD;
      this.out.connect(lim).connect(this.ctx.destination);
    }
    if (this.ctx.state === "suspended") this.ctx.resume();
  },
  tone(freq, start, dur, type = "sine", vol = .16) {
    const t = this.ctx.currentTime + start, o = this.ctx.createOscillator(), g = this.ctx.createGain();
    o.type = type; o.frequency.value = freq;
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(vol, t + .012); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
    o.connect(g).connect(this.out); o.start(t); o.stop(t + dur + .02);
  },
  play(name) {
    if (!this.on) return;
    this.ensure();
    if (name === "tick") this.tone(880, 0, .07, "sine", .07);
    if (name === "select") this.tone(988, 0, .16);
    if (name === "found") { this.tone(784, 0, .14); this.tone(1175, .12, .2); }
    if (name === "move") { this.tone(784, 0, .12); this.tone(988, .11, .12); this.tone(1319, .22, .26); }
    if (name === "error") { this.tone(196, 0, .28, "square", .07); this.tone(165, .2, .32, "square", .07); }
  },
};
function setSound(on) {
  Sound.on = on; localStorage.setItem("pv-sound", on ? "1" : "0");
  $("sound").setAttribute("aria-pressed", on);
  $("sound").title = on ? "Sound on (S)" : "Sound off (S)";
  if (on) { Sound.ensure(); Sound.play("select"); }
}

// ---------------------------------------------------------------- copy
function rejectText(msg, from, to) {           // from/to are 1-based box numbers
  if (msg === "box is empty") return [`Box ${from} is empty`, "Point at a box that has an object in it."];
  if (msg === "can't identify object") return [`Can't tell what's in box ${from}`, "Teach this object in Set up, then try again."];
  if (msg.startsWith("can't tell")) return [`Can't tell whether box ${to} is empty`, "Take a new empty-tray photo in Set up."];
  const m = msg.match(/has an? (\w+) in it/);
  if (m) return [`Box ${to} isn't empty`, `The ${objLower(m[1])} is in it. Point at an empty box instead.`];
  return [upper(msg), ""];
}

// returns [tone, badge, headline, detail]
function status(sel, setup, n, robot) {
  const f = sel.from + 1, t = sel.to + 1, obj = sel.obj ? objLower(sel.obj) : "object", first = sel.phase === "from";
  if (setup.calib) return setup.calib_one
    ? ["setup", "✎", `Redraw box ${setup.calib_i + 1}`, "Drag a rectangle around it on the camera picture."]
    : ["setup", "✎", `Draw box ${setup.calib_i + 1} of ${n}`, "Drag a rectangle around it on the camera picture."];
  switch (sel.state) {
    case "DWELLING": return first ? ["from", "1", `Hold still on box ${f}`, "Keep pointing until the bar fills."]
                                  : ["to", "2", `Hold still on box ${t}`, "Keep pointing until the bar fills."];
    case "AWAIT_CLEAR": return first ? ["from", "1", "Now move your hand away", `So the camera can see what's in box ${f}.`]
                                     : ["to", "2", "Now move your hand away", `So the camera can check box ${t} is empty.`];
    case "CLASSIFYING": return first ? ["from", "1", `Looking at box ${f}…`, "Keep your hand out of view for a moment."]
                                     : ["to", "2", `Checking box ${t} is empty…`, "Keep your hand out of view for a moment."];
    case "CHOOSE_DEST": return ["to", "2", `${upper(obj)} found. Point where it should go`, "Hold your finger over an empty box for one second."];
    case "DISPATCHED": return ["move", "3", `Moving the ${obj} to box ${t}`,
      `From box ${f}${gripText(sel.obj) ? ", " + gripText(sel.obj) : ""}. Keep hands clear until it's done.`];
    default:
      if (reject && performance.now() < reject.until) return ["bad", "!", reject.h, reject.d];
      if (sel.msg === "robot busy") return ["move", "3", "Wait for the robot to finish", "It's still completing the last move."];
      if (robot && robot.gate && !robot.armed)
        return ["idle", "▶", "Press START to move an object", "Shuffle objects freely: pointing only counts after START."];
      return ["idle", "1", "Point at an object to move it", "Hold your index finger over its box for one second."];
  }
}

// ---------------------------------------------------------------- render
let lastNatural = 0;
function budgetChart(arr, limit) {
  const svg = $("budget-chart"), top = limit * 1.25;
  const y = v => 52 - Math.min(v, top) / top * 44;
  const ly = y(limit);
  svg.querySelector(".limit").setAttribute("y1", ly); svg.querySelector(".limit").setAttribute("y2", ly);
  if (arr.length < 2) return;
  svg.querySelector(".series").setAttribute("points", arr.map((v, i) => `${(i / 79) * 300},${y(v)}`).join(" "));
}

// biggest camera picture that fits the screen height, keeping its shape; panels get the rest
function layoutCamera() {
  const nw = cam.naturalWidth || 640, nh = cam.naturalHeight || 480;
  const page = document.querySelector(".page"), ps = getComputedStyle(page);
  const innerW = page.clientWidth - parseFloat(ps.paddingLeft) - parseFloat(ps.paddingRight);
  const present = document.body.classList.contains("present"), narrow = window.innerWidth <= 860;
  const sideMin = present || narrow ? 0 : (document.body.classList.contains("setup-open") ? 460 : 380) + 16;
  const top = frameEl.getBoundingClientRect().top + window.scrollY;
  const below = present ? 20 : 63 + 16 + 26;   // room for the moves strip (fixed, so it never flip-flops)
  const availH = Math.max(220, window.innerHeight - top - below);
  const availW = Math.max(200, innerW - sideMin - 2);
  const s = narrow ? availW / nw : Math.min(availW / nw, availH / nh);
  cam.style.width = Math.floor(nw * s) + "px";
  cam.style.height = Math.floor(nh * s) + "px";
}
window.addEventListener("resize", layoutCamera);

// If the side panels are taller than the camera, show "Recent moves" in the gap under it
// (and hide the bottom strip so moves aren't shown twice). Otherwise keep the strip.
function fitRecent() {
  const present = document.body.classList.contains("present"), narrow = window.innerWidth <= 860;
  const col = document.body.classList.contains("setup-open") ? $("setup") : $("side");
  const gap = col.offsetHeight - frameEl.offsetHeight - 16;
  const show = !present && !narrow && gap >= 150;
  $("recent").hidden = !show;
  $("strip").hidden = show;
  if (show) $("recent").style.height = gap + "px";
}
new ResizeObserver(fitRecent).observe($("side"));
new ResizeObserver(fitRecent).observe($("setup"));
new ResizeObserver(fitRecent).observe(frameEl);

function onStateChange(sel) {
  if (sel.state === prevState) return;
  const was = prevState; prevState = sel.state;
  if (sel.state === "DWELLING") { reject = null; Sound.play("tick"); }
  else if (sel.state === "AWAIT_CLEAR" && was === "DWELLING") Sound.play("select");
  else if (sel.state === "CHOOSE_DEST" && was === "CLASSIFYING") Sound.play("found");
  else if (sel.state === "DISPATCHED") Sound.play("move");
  else if (sel.state === "REJECTED") {
    const [h, d] = rejectText(sel.msg, sel.from + 1, sel.to + 1);
    reject = { h, d, until: performance.now() + 4500 };
    Sound.play("error");
  }
}

function render() {
  const { sys, sel, setup, boxes, robot, hand } = S;
  onStateChange(sel);

  $("sys").textContent = `${sys.os} · ${sys.board}`;
  const link = robot.link || "simulated";
  $("link").dataset.link = link;
  $("link").textContent = link === "connected" ? "Robot arm connected" : "Robot arm: simulated";
  $("lamp").dataset.state = robot.busy ? "busy" : "ok";
  $("lamp-text").textContent = robot.busy ? "Robot moving" : "Live";

  // status bar
  const [tone, badge, h, d] = status(sel, setup, boxes.length, robot);
  $("status").dataset.tone = tone;
  $("badge").textContent = badge;
  $("instr").textContent = h;
  $("detail").textContent = d;
  // hold bar fills while pointing, then stays full while you move your hand away ("got it")
  $("hold").style.width = (sel.state === "DWELLING" ? sel.progress * 100 : sel.state === "AWAIT_CLEAR" ? 100 : 0) + "%";
  const counting = sel.state === "CHOOSE_DEST" && sel.time_left_ms != null;
  $("count").hidden = !counting;
  if (counting) $("count-n").textContent = Math.ceil(sel.time_left_ms / 1000);
  $("cancel").hidden = !busyMove(sel.state) || setup.calib;
  $("start").hidden = !robot.gate || robot.armed || busyMove(sel.state) || setup.calib;

  // boxes
  $("boxes").innerHTML = boxes.map((b, i) => {
    const role = i === sel.from ? "from" : i === sel.to ? "to" : "";
    const known = KNOWN.includes(b.label);
    const name = b.hand ? "Hand in the way" : known ? OBJ[b.label] : b.label === "empty" ? "Empty" : "Can't tell";
    const sub = b.hand ? "Waiting for a clear view" : b.label === "empty" ? "Free to place something"
      : known ? "Ready to pick" : setup.has_bg ? "Teach this object in Set up" : "Take an empty-tray photo first";
    const tag = role ? `<span class="role" data-r="${role}">${role === "from" ? "From" : "To"}</span>` : "<span></span>";
    return `<li data-role="${role}"><span class="bn">${i + 1}</span><div><div class="bo" data-dim="${known && !b.hand ? 0 : 1}">${name}</div><div class="bs">${sub}</div></div>${tag}</li>`;
  }).join("");

  // real-time health
  $("perf-os").textContent = `measured on ${sys.os}`;
  $("h-react").textContent = sys.react_ms != null ? (sys.react_ms / 1000).toFixed(1) : "–";
  $("h-ontime").textContent = sys.ontime_pct != null ? Math.floor(sys.ontime_pct) : "–";
  $("h-ontime").closest(".tile").dataset.good = sys.ontime_pct >= 99 ? 1 : 0;
  $("h-cpu").textContent = sys.cpu_pct != null ? Math.round(sys.cpu_pct) : "–";
  $("h-cpu").closest(".tile").dataset.good = sys.cpu_pct != null && sys.cpu_pct < 70 ? 1 : 0;
  $("h-frame-now").textContent = `${sys.frame_ms} ms now`;
  hist.fps.push(sys.frame_ms);
  if (hist.fps.length > 80) hist.fps.shift();
  budgetChart(hist.fps, sys.budget_ms || 200);
  $("t-fps").textContent = sys.fps.toFixed(1);
  $("t-hand").textContent = sys.hand_ms;
  $("t-frame").textContent = sys.frame_ms;
  $("t-jitter").textContent = sys.jitter_ms ?? "–";
  $("t-worst").textContent = sys.worst_ms;
  const lm = sys.last_move;
  $("t-breakdown").textContent = lm ? `identify ${(lm.identify_ms / 1000).toFixed(1)} s, choose ${lm.choose_s.toFixed(1)} s, robot ${lm.robot_s.toFixed(1)} s` : "–";
  $("t-cam").textContent = `${sys.cam.replace("x", " × ")}`;
  if (cam.naturalWidth && cam.naturalWidth !== lastNatural) { lastNatural = cam.naturalWidth; layoutCamera(); }
  $("perf-chip").innerHTML = `<span><b>${sys.fps.toFixed(1)}</b> fps</span><span><b>${sys.hand_ms}</b> ms hand model</span><span>${esc(sys.os)}</span>`;

  // details (for judges)
  $("d-link").textContent = link === "connected" ? "Connected" : "Simulated (arm not wired yet)";
  $("d-time").textContent = robot.last ? clock(robot.last_t) : "–";
  $("d-cmd").textContent = robot.last || "No command sent yet";
  $("d-boxes").innerHTML = boxes.map((b, i) => KNOWN.includes(b.label)
    ? `<li><span>Box ${i + 1}: ${OBJ[b.label]}, ${Math.round(b.conf * 100)}% sure</span><span class="num">grip ${b.grip[0]}–${b.grip[1]}</span></li>` : "").join("");

  renderMoves(S.moves);
  renderSetup(setup, boxes.length, hand);
  frameEl.classList.toggle("drawing", setup.calib);
  draw();
}

function renderMoves(moves) {
  const sig = JSON.stringify(moves);
  if (sig === lastMoves) return;
  lastMoves = sig;
  const finished = moves.filter(m => m.status !== "moving");
  const done = finished.filter(m => m.status === "done");
  const avg = done.length ? (done.reduce((a, m) => a + (m.secs || 0), 0) / done.length).toFixed(1) : null;
  $("stats").innerHTML = !moves.length ? "No moves yet. They'll show up here."
    : `<b>${done.length}</b> of ${finished.length} moves done` + (avg ? ` · avg <b>${avg} s</b>` : "");
  $("chips").innerHTML = moves.slice(0, 6).map(m => {
    const icon = { done: "✓", moving: "↻", rejected: "✕", cancelled: "–", "no-response": "✕" }[m.status] || "•";
    const path = m.from && m.to ? `${m.from} → ${m.to}` : m.from ? `from ${m.from}` : "";
    const why = m.status === "rejected" ? rejectText(m.note, m.from, m.to)[0] : m.status === "cancelled" ? "cancelled" : "";
    return `<li class="chip" data-r="${m.status}"><i>${icon}</i>${m.obj ? objName(m.obj) : "Move"} <small>${path}${why ? " · " + esc(why.toLowerCase()) : ""}</small></li>`;
  }).join("");
  $("recent-stats").innerHTML = moves.length ? $("stats").innerHTML : "";
  $("recent-list").innerHTML = !moves.length ? `<li class="empty">No moves yet. Point at an object to start one.</li>`
    : moves.slice(0, 12).map(m => {
      const icon = { done: "✓", moving: "↻", rejected: "✕", cancelled: "–", "no-response": "✕" }[m.status] || "•";
      const path = m.from && m.to ? `Box ${m.from} → Box ${m.to}` : m.from ? `From box ${m.from}` : "";
      const why = m.status === "rejected" ? rejectText(m.note, m.from, m.to)[0] : m.status === "cancelled" ? m.note
                : m.status === "done" && m.secs != null ? `${m.secs} s` : m.status === "moving" ? "moving now" : "";
      const grip = m.obj ? gripText(m.obj) : "";
      return `<li data-r="${m.status}"><i>${icon}</i><b>${m.obj ? objName(m.obj) : "Move"}</b>
        <span class="what">${path}${grip ? " · " + grip : ""}${why ? `<small>${esc(why)}</small>` : ""}</span><time>${clock(m.t)}</time></li>`;
    }).join("");
  const RES = { done: "Done", moving: "Moving", rejected: "Rejected", cancelled: "Cancelled", "no-response": "No reply from robot" };
  $("moves").innerHTML = moves.length ? moves.map(m => {
    const why = m.status === "rejected" ? rejectText(m.note, m.from, m.to)[0] : m.status === "cancelled" ? m.note : "";
    return `<tr><td class="time">${clock(m.t)}</td><td>${m.obj ? objName(m.obj) : "–"}</td><td>${m.from ? "Box " + m.from : "–"}</td>
      <td>${m.to ? "Box " + m.to : "–"}</td><td class="num">${m.grip ? (GRIP[m.obj] ? GRIP[m.obj] + " " : "") + m.grip[0] + "–" + m.grip[1] : "–"}</td>
      <td class="num">${m.secs != null ? m.secs + " s" : "–"}</td><td><span class="res" data-r="${m.status}">${RES[m.status] || m.status}</span>${why ? `<span class="why">${esc(why)}</span>` : ""}</td></tr>`;
  }).join("") : `<tr><td colspan="7" style="color:var(--muted)">No moves yet.</td></tr>`;
}

function renderSetup(setup, n, hand) {
  const boxesDone = setup.boxes_set !== false, bgDone = setup.has_bg;
  const taught = KNOWN.filter(k => setup.counts[k] >= TEACH_GOAL).length;
  // done when every object you've started teaching has enough examples
  const started = KNOWN.filter(k => setup.counts[k] > 0);
  const teachDone = started.length > 0 && started.every(k => setup.counts[k] >= TEACH_GOAL);
  const tasks = [["task-boxes", boxesDone, setup.calib ? "Drawing…" : boxesDone ? `${n} boxes marked` : "Not done"],
                 ["task-bg", bgDone, bgDone ? "Photo taken" : "Not done"],
                 ["task-teach", teachDone, `${taught} of 3 objects ready`]];
  let activeSet = false;
  for (const [id, done, txt] of tasks) {
    $(id).dataset.done = done ? 1 : 0;
    $(id).dataset.active = !done && !activeSet ? 1 : 0;
    if (!done) activeSet = true;
    $(id.replace("task-", "ts-")).textContent = txt;
  }
  $("draw").textContent = setup.calib && !setup.calib_one ? "Stop drawing" : "Draw all 4";
  const rd = $("redraw");
  if (rd.children.length !== n) rd.innerHTML = Array.from({ length: n }, (_, i) => `<button data-i="${i}" title="Redraw box ${i + 1}">${i + 1}</button>`).join("");
  [...rd.children].forEach((b, i) => b.dataset.on = setup.calib && setup.calib_one && setup.calib_i === i ? 1 : 0);
  $("bg-warn").hidden = !hand.pts;
  // build the Teach rows once, then only update them - rebuilding every poll
  // replaced the buttons mid-click, so most clicks never registered
  const tl = $("teach");
  if (tl.children.length !== KNOWN.length) tl.innerHTML = KNOWN.map((k, i) => `<li><span class="tn">${OBJ[k]}</span>
      <div class="bar"><span></span></div><span class="tc num"></span>
      <button class="btn" data-teach="${i + 1}">Teach</button></li>`).join("");
  KNOWN.forEach((k, i) => {
    const li = tl.children[i], c = setup.counts[k], ok = c >= TEACH_GOAL;
    li.dataset.ok = ok ? 1 : 0;
    li.querySelector(".bar").title = `${c} examples`;
    li.querySelector(".bar span").style.width = `${Math.min(100, c / TEACH_GOAL * 100)}%`;
    li.querySelector(".tc").textContent = ok ? "Ready" : `${c} of ${TEACH_GOAL}`;
  });
  $("mask").checked = setup.mask;
  $("log").innerHTML = (S.log || []).slice(-8).map(l => `<li>${esc(l)}</li>`).join("");
}

// ---------------------------------------------------------------- camera overlay
function sizeCanvas() {
  const r = cam.getBoundingClientRect(), f = frameEl.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  cv.style.left = (r.left - f.left) + "px"; cv.style.top = (r.top - f.top) + "px";
  cv.style.width = r.width + "px"; cv.style.height = r.height + "px";
  cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr);
  draw();
}
new ResizeObserver(sizeCanvas).observe(cam);
new ResizeObserver(sizeCanvas).observe(frameEl);

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
function tag(ctx, x, y, text, bg, fg, size) {
  ctx.font = `600 ${size}px "Inter", "Segoe UI", sans-serif`;
  const pad = size * .7, w = ctx.measureText(text).width + pad * 2, h = size * 1.9;
  ctx.fillStyle = bg; roundRect(ctx, x, y, w, h, 7); ctx.fill();
  ctx.fillStyle = fg; ctx.fillText(text, x + pad, y + h * .68);
  return w;
}

function draw() {
  const dpr = window.devicePixelRatio || 1, W = cv.width / dpr, H = cv.height / dpr;
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  if (!S || !online) return;
  const { sel, setup, hand } = S;
  const fs = Math.max(11, Math.min(17, W / 52));   // label size follows picture size

  S.boxes.forEach((b, i) => {
    const x = b.rect[0] * W, y = b.rect[1] * H, w = b.rect[2] * W, h = b.rect[3] * H;
    let role = i === sel.from ? "from" : i === sel.to ? "to" : "";
    if (setup.calib) role = i === setup.calib_i ? "calib" : "";
    const pointedAt = hand.pointing && hand.over === i && !role && !setup.calib;
    ctx.save(); roundRect(ctx, x + 1.5, y + 1.5, w - 3, h - 3, 10);
    if (role === "from") { ctx.fillStyle = "rgba(59,130,246,.16)"; ctx.fill(); ctx.strokeStyle = C.blue; ctx.lineWidth = 3.5; }
    else if (role === "to") { ctx.fillStyle = "rgba(245,165,36,.16)"; ctx.fill(); ctx.strokeStyle = C.amber; ctx.lineWidth = 3.5; ctx.setLineDash([12, 7]); }
    else if (role === "calib") { ctx.strokeStyle = C.amber; ctx.lineWidth = 2.5; ctx.setLineDash([7, 5]); }
    else if (pointedAt) { ctx.strokeStyle = "rgba(233,236,240,.85)"; ctx.lineWidth = 2.5; }
    else { ctx.strokeStyle = C.line; ctx.lineWidth = 1.5; if (setup.calib) ctx.setLineDash([4, 6]); }
    ctx.stroke(); ctx.restore();

    // label: box number + what's inside, sized for reading at a distance
    ctx.save(); roundRect(ctx, x, y, w, h, 10); ctx.clip();
    const unknown = !b.hand && b.label === "unknown" && setup.has_bg;  // something's there, but not a taught object
    const what = b.hand ? "Hand" : KNOWN.includes(b.label) ? OBJ[b.label] : b.label === "empty" ? "Empty"
      : unknown ? "Unknown" : "";
    let txt = what ? `${i + 1} ${what}` : `${i + 1}`;
    // narrow box: shrink the text to fit (down to 60%) before giving up on the word
    let lf = fs;
    ctx.font = `600 ${lf}px "Inter", sans-serif`;
    while (lf > fs * 0.6 && ctx.measureText(txt).width + lf * 1.6 > w - 12) {
      lf -= 1; ctx.font = `600 ${lf}px "Inter", sans-serif`;
    }
    if (ctx.measureText(txt).width + lf * 1.6 > w - 12) txt = unknown ? `${i + 1} ?` : `${i + 1}`;
    if (unknown && !role) tag(ctx, x + 6, y + 6, txt, C.amber, "#1A1203", lf);
    else if (role === "from") tag(ctx, x + 6, y + 6, txt, C.blue, "#fff", lf);
    else if (role === "to" || role === "calib") tag(ctx, x + 6, y + 6, txt, C.amber, "#1A1203", lf);
    else tag(ctx, x + 6, y + 6, txt, "rgba(8,10,13,.8)", what === "Empty" ? "#A1A9B6" : "#E9ECF0", lf);
    ctx.restore();
  });

  if (hand.pts) {
    ctx.strokeStyle = "rgba(233,236,240,.5)"; ctx.lineWidth = 1.6;
    ctx.beginPath();
    for (const [a, b] of HAND) { ctx.moveTo(hand.pts[a][0] * W, hand.pts[a][1] * H); ctx.lineTo(hand.pts[b][0] * W, hand.pts[b][1] * H); }
    ctx.stroke();
  }
  if (hand.tip) {
    const tx = hand.tip[0] * W, ty = hand.tip[1] * H, col = sel.phase === "to" ? C.amber : C.blue, R = Math.max(22, W / 30);
    if (sel.state === "DWELLING") {
      ctx.lineWidth = 5; ctx.lineCap = "round";
      ctx.fillStyle = "rgba(6,8,11,.55)"; ctx.strokeStyle = "rgba(46,53,66,.9)";
      ctx.beginPath(); ctx.arc(tx, ty, R, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      ctx.strokeStyle = col;
      ctx.beginPath(); ctx.arc(tx, ty, R, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * sel.progress); ctx.stroke();
      ctx.lineCap = "butt";
    }
    ctx.fillStyle = hand.pointing ? col : C.text;
    ctx.beginPath(); ctx.arc(tx, ty, 6, 0, Math.PI * 2); ctx.fill();
  }
  if (drag) {
    ctx.strokeStyle = C.amber; ctx.lineWidth = 2; ctx.setLineDash([6, 4]);
    ctx.strokeRect(Math.min(drag.a[0], drag.b[0]) * W, Math.min(drag.a[1], drag.b[1]) * H,
                   Math.abs(drag.b[0] - drag.a[0]) * W, Math.abs(drag.b[1] - drag.a[1]) * H);
    ctx.setLineDash([]);
  }
}

// ---------------------------------------------------------------- drawing boxes
function pos(e) {
  const r = cv.getBoundingClientRect();
  return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
}
cv.addEventListener("pointerdown", e => {
  if (!S || !S.setup.calib) return;
  drag = { a: pos(e), b: pos(e) };
  try { cv.setPointerCapture(e.pointerId); } catch (_) {}
  e.preventDefault();
});
cv.addEventListener("pointermove", e => { if (drag) { drag.b = pos(e); draw(); } });
cv.addEventListener("pointercancel", () => { drag = null; draw(); });
cv.addEventListener("pointerup", () => {
  if (!drag) return;
  const [a, b] = [drag.a, drag.b]; drag = null;
  send(`/rect?x0=${Math.min(a[0], b[0])}&y0=${Math.min(a[1], b[1])}&x1=${Math.max(a[0], b[0])}&y1=${Math.max(a[1], b[1])}`);
  draw();
});

// ---------------------------------------------------------------- controls
function toggleSetup(open) {
  const show = open ?? $("setup").hidden;
  $("setup").hidden = !show; $("side").hidden = show;
  document.body.classList.toggle("setup-open", show);
  layoutCamera();
  $("setup-toggle").setAttribute("aria-expanded", show);
  $("setup-toggle").textContent = show ? "Done" : "Set up";
  try { localStorage.setItem("pv-setup", show ? "1" : "0"); } catch {}  // stay on Set up after a refresh
}
function togglePresent() {
  const on = !document.body.classList.contains("present");
  document.body.classList.toggle("present", on);
  if (on && document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {});
  if (!on && document.fullscreenElement) document.exitFullscreen().catch(() => {});
  layoutCamera();
}
document.addEventListener("fullscreenchange", () => { if (!document.fullscreenElement) document.body.classList.remove("present"); layoutCamera(); });

$("setup-toggle").addEventListener("click", () => toggleSetup());
try { if (localStorage.getItem("pv-setup") === "1") toggleSetup(true); } catch {}
$("sound").addEventListener("click", () => setSound(!Sound.on));
$("help").addEventListener("click", () => $("help-dlg").showModal());
$("present").addEventListener("click", togglePresent);
$("all-moves").addEventListener("click", () => $("moves-dlg").showModal());
$("recent-all").addEventListener("click", () => $("moves-dlg").showModal());
document.querySelectorAll("[data-close]").forEach(b => b.addEventListener("click", () => b.closest("dialog").close()));
document.querySelectorAll("dialog").forEach(d => d.addEventListener("click", e => { if (e.target === d) d.close(); }));
$("cancel").addEventListener("click", () => cmd("cancel"));
$("start").addEventListener("click", () => cmd("start"));
$("draw").addEventListener("click", () => key("c"));
$("redraw").addEventListener("click", e => { const b = e.target.closest("button"); if (b) cmd("redraw", "&i=" + b.dataset.i); });
$("bg").addEventListener("click", () => key("b"));
$("teach").addEventListener("click", e => { const b = e.target.closest("[data-teach]"); if (b) cmd("teach", "&k=" + b.dataset.teach); });
$("forget").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.k === "all") {
    if (confirm("Delete every taught example for the pill bottle, squeeze bottle and pills? You'll need to teach them again.")) key("x");
  } else {
    const name = OBJ[KNOWN[b.dataset.k - 1]];
    if (confirm(`Delete the taught examples for ${name}? The other objects stay.`)) cmd("forget", "&k=" + b.dataset.k);
  }
});
$("forget-bg").addEventListener("click", () => {
  if (confirm("Delete the empty-tray photo? Take a new one right after, with every box empty.")) cmd("forgetbg");
});
$("mask").addEventListener("change", e => { if (S && e.target.checked !== S.setup.mask) key("m"); });

document.addEventListener("keydown", e => {
  if (e.target.closest("input, textarea, select") || e.ctrlKey || e.metaKey || e.altKey || document.querySelector("dialog[open]")) return;
  const k = e.key.toLowerCase();
  if (k === "f") togglePresent();
  else if (k === "s") setSound(!Sound.on);
  else if (e.key === "?") $("help-dlg").showModal();
  else if (k === "escape") { if (document.body.classList.contains("present")) togglePresent(); else if (S && busyMove(S.sel.state)) cmd("cancel"); }
  else if (["1", "2", "3"].includes(k)) cmd("teach", "&k=" + k);
  else if (["c", "b", "m"].includes(k)) key(k);
});

// ---------------------------------------------------------------- live updates
function reconnectVideo() { cam.src = "/stream?t=" + Date.now(); }
cam.addEventListener("error", () => setTimeout(reconnectVideo, 2000));

function setOffline() {
  online = false;
  $("lamp").dataset.state = "lost"; $("lamp-text").textContent = "Connection lost";
  $("status").dataset.tone = "bad"; $("badge").textContent = "!";
  $("instr").textContent = "Can't reach the robot";
  $("detail").textContent = "Check it's switched on and on the same Wi-Fi. This page reconnects by itself.";
  $("offline").hidden = false;
  draw();
}

async function poll() {
  try {
    const r = await fetch("/state", { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    const st = await r.json();
    if (st.sel) {
      if (!online) { online = true; $("offline").hidden = true; if (fails) reconnectVideo(); }
      fails = 0; S = st; render();
    }
  } catch (_) { if (++fails === 3) setOffline(); }
  setTimeout(poll, 120);
}
$("sound").setAttribute("aria-pressed", Sound.on);
$("sound").title = Sound.on ? "Sound on (S)" : "Sound off (S)";
// browsers only allow audio after the first click/tap on the page
document.addEventListener("pointerdown", () => { if (Sound.on) Sound.ensure(); }, { once: true });
cam.addEventListener("load", layoutCamera);
layoutCamera();
poll();
