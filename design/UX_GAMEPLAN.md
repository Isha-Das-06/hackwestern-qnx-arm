# PickVision console: UX gameplan

Goal: anyone can walk up, point, and move an object **without being told how**.
Judges should understand what's happening in a few seconds.

The word for "maximum easyness" is **usability**. "Good UI + easy to use" together = good **UX** (user experience).

---

## 1. Who uses it, and where they're looking

| Person | Where they are | What they need |
|---|---|---|
| **The pointer** (you, or a judge trying it) | Standing at the table, 1–2 m from the screen, looking at the **robot and boxes**, not the screen | One big instruction, and to know their hold "counted" without reading anything |
| **Judges watching** | Next to the screen, 3 min per judge | What's happening, that it's real-time on QNX, and that it's safe |
| **You during set up** | At the laptop | A short checklist that tells you what's done and what's next |

**This changes everything.** Right now the page is built for someone sitting at a desk reading it. The main user is standing away from it with their hand in the air.

---

## 2. What's wrong right now (measured on a 1920×1000 screen)

| # | Problem | Why it hurts | Rule it breaks |
|---|---|---|---|
| 1 | **Instruction text is 22 px.** You can't read it from 1–2 m. | The pointer can't tell what to do next | Visibility of system status |
| 2 | **Camera shows at 640×480** (its raw size) in a 1920-wide window. About 2/3 of the screen is empty black. | The most important thing is small | Visual hierarchy |
| 3 | **The hold ring is only drawn at the fingertip, about 48 px wide.** No sound. | You have to stare at a small circle on the screen while pointing at the table | Feedback |
| 4 | **Rejections flash for 1.5 s** ("Box 1 already has a cup") then vanish | People miss *why* it didn't work | Help users recognise and recover from errors |
| 5 | **The 10 s "choose a destination" limit is invisible.** It just cancels. | Feels like a bug | Visibility of system status |
| 6 | **The same info shows 3–4 times**: headline, step tracker, camera caption, box list, box labels on the video | Eyes don't know where to go | Minimalist design |
| 7 | **The right column is engineer info**: confidence %, grip numbers, "QNX control task", raw `[pick]` text | Clutters the operator's view. Useful to judges, but not first | Match the user's world |
| 8 | **The Activity table is below the fold** | The results of moves are hidden | Visibility |
| 9 | **Set up is a pile of buttons with no order.** Teaching needs "pick Box N, then click Cup", which is easy to get wrong. | Easy to teach the wrong box or skip the empty-tray photo | Error prevention, recognition over recall |
| 10 | **Draw boxes forces all 4 in order, with no undo.** One bad box means redrawing all 4. | Frustrating | User control and freedom |
| 11 | **"Robot: Ready"** shows even though the robot link is still simulated | Judges may ask, and it's not honest yet | Honesty |
| 12 | Grey helper text (`#5C6573` on `#11141A`) is about 3:1 contrast | Hard to read on a projector | Accessibility (aim for 4.5:1) |

---

## 3. Research this is based on

- **Hold-to-select (dwell) interfaces** (Microsoft's mixed-reality guidance):
  - Wait about 150–250 ms before showing hold feedback, so a passing glance doesn't start it.
  - Show continuous progress, and a clear "done" moment.
  - Make targets large.
  - Don't make people look back and forth between where they're pointing and a far-away result.
  - Our 1 s hold is fine for first-time users.
- **Industrial operator screens (ISA-101 "high-performance HMI"):**
  - Keep normal state calm and low-contrast.
  - Make the *abnormal* thing (a rejection, a fault) the highest-contrast thing on screen.
  - Build around the operator's task, not the machine's parts.
  - Use bars and rings instead of bare numbers.
- **Nielsen's 10 usability heuristics:**
  - Show system status quickly.
  - Prevent errors instead of explaining them afterwards.
  - Let people undo.
  - Recognition over recall.
  - Minimal design.

---

## 4. The new layout

```
┌───────────────────────────────────────────────────────────────────────────┐
│ PickVision                       QNX 8.0 · Raspberry Pi 4B   ● Live  [⚙ Set up] │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│   ①  Point at an object              ●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 72%  │  ← STATUS BAR
│      Hold your finger over its box   (hold bar fills, same colour as ring)  │    big, readable
│                                                                           │    from 2 m
├─────────────────────────────────────────────────────┬─────────────────────┤
│                                                     │  1  Cup      ← From │
│                                                     │  2  Block           │
│          CAMERA (fills the space, 4:3)              │  3  Empty           │
│          boxes drawn on top, labelled               │  4  Empty    → To   │
│          by what's inside                           ├─────────────────────┤
│                                                     │  10 fps   67 ms     │
│                                                     │  real-time on QNX   │
├─────────────────────────────────────────────────────┴─────────────────────┤
│ Last moves:  ✓ Cup 4→3   ✗ Block 1→2 (box full)   ✓ Block 2→1    [All ▸]   │
└───────────────────────────────────────────────────────────────────────────┘
```

- **One status bar at the top is the "voice" of the robot.** It's big (about 44–56 px), with a step number, the instruction, a hold bar that fills, and a countdown when there's a time limit. Its colour shows the state:
  - neutral: waiting
  - blue: picking the object
  - amber: picking the destination
  - green: moving
  - red: problem
- **The camera fills the rest.** Box labels are drawn on the video ("Cup", "Empty"), so you don't have to look elsewhere.
- **The side column gets thinner:** the 4 boxes, plus 2 speed numbers. Confidence and grip go into a "Details" toggle for judges.
- **Last moves become one line** at the bottom, always visible. The full table opens on click.

---

## 5. Gameplan (in order of impact)

### Phase 1: "Readable from 2 metres" (biggest win, about 1 h)
1. **Big status bar:** instruction at 44–56 px, coloured by state, step number on the left.
2. **Hold bar in the status bar.** It fills over 1 s, in the same colour as the ring on the video, so you can see progress with a quick glance.
3. **Camera scales up** to fill the space (keeping 4:3). No more 640 px picture on a 1920 screen.
4. **Sounds** (built into the browser, nothing to install):
   - soft tick when a hold starts
   - "ding" when a box is selected
   - double ding when the robot moves
   - low buzz on a rejection

   Mute button in the top bar. *This is the biggest one for the pointer, who isn't looking at the screen.*
5. **Rejections stay up for 4 s** in red, with the fix ("Choose an empty box").
6. **Countdown** while choosing the destination: "Point where the cup goes · 7 s".

### Phase 2: "Clean for judges" (about 45 min)
7. **Remove duplicates:** drop the separate step tracker (the status bar has the step) and the camera caption.
8. **Side column:** the 4 boxes as big rows (number, object, From/To), plus speed numbers. Grip, confidence and the raw `[pick]` text move under **Details** (closed by default).
9. **"Last moves" strip** always visible at the bottom. The full Activity table opens from it.
10. **Presentation mode** (press **F**): full screen, camera plus status bar plus speed only. For the demo table.
11. **Robot link shows the truth:** "Robot link: simulated" until the real QNX control task is connected, then "Connected".
12. **Contrast fix:** all small text at least 4.5:1.

### Phase 3: "Set up that can't go wrong" (about 1 h)
13. **Set up becomes a 3-step checklist** with ✓ marks: ① Draw boxes → ② Empty-tray photo → ③ Teach objects. Each step unlocks the next and says what to do.
14. **Redraw one box:** click a box, then "Redraw box 3". No more redrawing all 4.
15. **Teaching without choosing a box:** put the object in *any* box, then click "Teach cup". The app picks the box that isn't empty. If 2 boxes have something in them, it asks.
16. **Empty-tray photo check:** before taking it, warn if a hand or object is visible.
17. **Teaching progress per object:** "Cup 5/5 ✓, Block 5/5 ✓, Egg 0/5". So you know when you're done.

### Phase 4: Polish (optional, about 30 min)
18. One short page-load animation for the status bar. No other animation.
19. Keyboard shortcuts listed in a small "?" panel.
20. Session stats for judges: moves done, success rate, average move time.

---

## 6. What needs backend changes (Python)

| Item | Change |
|---|---|
| Countdown (6) | Add `time_left_ms` to `/state` while choosing the destination |
| Redraw one box (14) | New command `/cmd?c=redraw&i=N`: draws only box N |
| Teach any box (15) | Key `1/2/3` with no box chosen → use the one non-empty box (the classifier already measures how full each box is) |
| Empty-photo check (16) | Refuse `b` if a hand is in view (already done) or if a box doesn't look empty compared to the last photo |
| Robot link (11) | `robot.link = "simulated"` now, `"connected"` once the real control task is wired |

Everything else is page-only (HTML/CSS/JS). It's the same on the laptop and the Pi because the sync copies `python/web/`.

---

## 7. How we'll know it's better

- A friend who has never seen it moves an object **without help, within 30 s**.
- From 2 m away you can say what step it's on.
- A judge can say "it's running real-time on QNX" after one glance.
- Set up from scratch takes **under 3 minutes**.

## Sources
- [Microsoft: gaze and dwell (eyes)](https://learn.microsoft.com/en-us/windows/mixed-reality/design/gaze-and-dwell-eyes)
- [Microsoft: head-gaze and dwell](https://learn.microsoft.com/en-us/windows/mixed-reality/design/gaze-and-dwell-head)
- [Nielsen Norman Group: 10 usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/)
- [Control Global: best practices in high-performance HMI design](https://www.controlglobal.com/visualize/hmi/article/11380465/human-machine-interface-best-practices-in-high-performance-hmi-design)
- [Yokogawa: ISA-101, toward a more effective HMI strategy](https://yokogawa.com/us/library/resources/media-publications/isa-101-toward-a-more-effective-hmi-strategy)
