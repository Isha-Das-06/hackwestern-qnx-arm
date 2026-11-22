# Live Hackathon Demo Pitch at Science-Fair Judging (3-min demo + 1-min Q&A, no slides)

Scope note: These notes come from about 15 searches and fetches (Nov 2026). Sources include judges' first-hand notes (dev.to, July 2026), a multi-time winner (Substack, Apr 2026), organizer guides (MLH Hackathon Guide, Builderbase), a university showcase tip sheet (UCI BB Comp 2025), a robotics demo veteran (General Robots, 2023), and QNX's official docs. The JetBrains "notes from the judging table" post (June 2026) came up in several searches but returned HTTP 403, so the only claims used from it are ones that search snippets attribute to a judge's notes. The thenewstack hardware-demo article also returned 403. The Hack the North 2025 criteria page (Notion) would not render, so the HTN facts below come from search snippets only. Most sources are opinion and practitioner experience, not controlled studies.

## Q1. What do experienced judges and winners recommend for the first 15-30 seconds?

### Takeaway
Start by saying plainly what the product is and who it's for ("this is a tool that does X for Y"). Use a short, concrete, human problem hook, then get to the working thing fast. Judges report that the score is largely set in the first 30 seconds, so rehearse that part word for word.

### Cited Findings
- A judge of three hackathons in July 2026 says strong teams opened with a plain statement: "this is a tool that does X for Y." Teams that opened with context spent time before the judge understood the product — [Kurbaitaev, dev.to, "What judges actually score"](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l)
- The same judge says to rehearse the first 30 seconds out loud, because that's where the score is largely set — [Kurbaitaev, dev.to](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l)
- Projects that survive the judges' debrief have a one-line identity. Define that sentence before coding. A search snippet attributed to a judge's notes suggests picking the sentence you want a judge to repeat to another judge an hour later — [Kurbaitaev, dev.to](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l); snippet from [JetBrains blog, June 2026](https://blog.jetbrains.com/ai/2026/06/how-to-win-a-hackathon-notes-from-the-judging-table/) (full page not retrievable)
- Builderbase guide: problem in 15-20s (what's broken, who's affected, concrete and human), then the solution in one simple sentence in 15-20s. "Open with the problem, not the product name." A striking statistic or a specific person works well — [Builderbase Builder's Guide ch.14](https://intercom.help/builderbase/en/articles/14836128-builder-s-guide-ch-14-crafting-a-demo-that-lands)
- UCI showcase guide: "Hook with a story" (example: "Did you know 500k semi-trucks crash annually?" from the 2024 Sentinel team). Greet judges warmly, help them transition from the previous team, stand up, make eye contact. State problem, solution and impact in under 60 seconds — [UCI BB Comp Showcase Tips 2025 (PDF)](https://bbcomp.tech.uci.edu/wp-content/uploads/2025/05/BB-Comp-Showcase-Tips-and-Tricks-2025.pdf)
- Multi-time winner: open with the problem and what the product does, not the tech stack. Explain technical details only after the audience cares — [John Kim, "How To Win Hackathons", Push To Prod, Apr 2026](https://getpushtoprod.substack.com/p/how-to-win-hackathons)
- Name the exact user. "Athletes" is weaker than a specific, described person — [Kurbaitaev, dev.to](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l)

### Inferences
- The sources differ slightly. Kurbaitaev puts "what it is" first, while Builderbase and UCI put the problem hook first. They can be combined in one breath of about 10 seconds: a one-sentence hook naming a specific person or problem, then "We built X, which does Y for them," then "Let me show you." Pressing "go" on the hardware by about 0:20-0:30 fits every source.
- At table judging, judges arrive still thinking about the previous team (UCI). Saying the one-line identity in the first seconds, ideally matching a sign on the table, helps them reset.

### Gaps
- None of the sources tested hook styles (statistic vs. story vs. "what it is") against each other. The advice is practitioner opinion.

## Q2. How should time be split between problem, live demo, and tech explanation? Show vs. tell?

### Takeaway
Use most of the time to show. Across sources, about 50-65% of a 3-minute slot goes to the live demo. The problem and solution get about 30-40s, the tech or "how" gets about 30s (woven into the demo where possible), and impact or next steps get about 15-30s. A working end-to-end demo beats a more ambitious project shown as slides "almost every time."

### Cited Findings
- Builderbase structure for 90s-3min: problem 15-20s, solution 15-20s, live demo 60-90s, impact 10-15s, ask 5-10s. Practice at least 3 times with a timer, and expect the first run to be too long — [Builderbase ch.14](https://intercom.help/builderbase/en/articles/14836128-builder-s-guide-ch-14-crafting-a-demo-that-lands)
- A 3-minute split seen in search results: 30s problem and solution, 90s demo, 30s tech stack, 30s next steps — [Reskilll blog, "Pitch in 3 minutes and win" (2026)](https://blogs.reskilll.com/hackathon-demo-presentation-tips-pitch-3-minutes-win-2026/) (snippet only, not fetched)
- A live working product beats a more ambitious project shown as slides. Cut scope until "something end-to-end runs." Slide decks did not move scores, and one fallback screenshot was enough — [Kurbaitaev, dev.to](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l)
- "Build a demo, not a product." Make the happy path work and polish it. "The one wow moment has to be real." — [John Kim, Push To Prod](https://getpushtoprod.substack.com/p/how-to-win-hackathons)
- Demo one feature that works fully rather than a broad product that might crash. Use an input you know works — [Builderbase ch.14](https://intercom.help/builderbase/en/articles/14836128-builder-s-guide-ch-14-crafting-a-demo-that-lands)
- UCI: "Tactile is better." Let judges physically engage with or "play" with the prototype. Showcase 3-4 standout features, not everything. Ask visitors questions to involve them — [UCI BB Comp 2025](https://bbcomp.tech.uci.edu/wp-content/uploads/2025/05/BB-Comp-Showcase-Tips-and-Tricks-2025.pdf)
- Hack the North 2025 guidance (snippet): 5 minutes in the judging room with about 3 minutes of presenting and demoing, and you will be cut off at the 5-minute mark — [HTN 2025 judging instructions/FAQ](https://hackthenorth.notion.site/2025-judging-instructions-faq) (snippet only; page would not render)
- MLH science-fair planning gives judges about 3 minutes per team. The planning formula is 2 min presentation and demo, 1 min questions and scoring, 1 min travel — [MLH Hackathon Guide, Judging Plan](https://guide.mlh.com/general-information/judging-and-submissions/judging-plan)

### Inferences
- A suggested split for this event's 3 minutes: 0:00-0:25 identity and hook. 0:25-2:15 live demo, narrated so each step shows one claim, including one "wow" moment. 2:15-2:45 one technical sentence plus one honest limitation. 2:45-3:00 a memorable closing line. Then 1 minute of Q&A.
- Explain the tech while the demo runs ("this panel is the QNX scheduler trace; watch the deadline-miss counter stay at zero"). With no slides, the hardware and any live dashboard on a laptop or monitor stand in for the deck. A printed one-page diagram or poster on the table is usually allowed. Check the rules, since "no slide decks" may or may not cover posters.

### Gaps
- None of the sources give an evidence-based optimal ratio. All splits are recommendations.

## Q3. Best practices for hardware/robotics demos: reliability, backup video, rehearsal, and what to do when it fails live

### Takeaway
Freeze the code early. Demo only what has worked 3 times in a row. Assume Wi-Fi will fail. Bring spares and power. Assign a "Talker" and a "Fixer." Keep a short backup video and partial-result screenshots one tap away. If it fails, say so calmly, switch to the backup, explain what should have happened, and resume live if it recovers. Never debug in front of the judge.

### Cited Findings
- Freeze code well before the demo and show features that have been stable, not ones finished the night before. "Make sure your demo works 3x in a row." If it isn't reliable without demo pressure, use a video instead — [Benjie Holson, "Nailing the Demo", General Robots, Mar 2023](https://generalrobots.substack.com/p/nailing-the-demo)
- Run the full demo, talking points included, ahead of time, with someone playing the VIP and asking hard questions — [Holson](https://generalrobots.substack.com/p/nailing-the-demo)
- "If you aren't paranoid about wifi, it will sink your demo." Reduce Wi-Fi reliance, prepare wired backups, or bring your own router. A crowd of phones makes the network worse — [Holson](https://generalrobots.substack.com/p/nailing-the-demo)
- Bring spare robots if possible. In one case a spare caught fire during a demo for Google's founders and a third robot saved it. "It's almost always better to swap robots than debug during a demo." — [Holson](https://generalrobots.substack.com/p/nailing-the-demo)
- Split roles: a "Talker" calmly explains problems and puts them in context, and a "Fixer" handles technical issues, decides when to swap to backup, and has the start command ready. Print the checklist and cross items off by hand, because people miss steps on screens under stress. Before the VIP arrives, restart, check batteries (replace any below 50%), check logs, and put the cursor on the start command — [Holson](https://generalrobots.substack.com/p/nailing-the-demo)
- Bring extra batteries, chargers, extension cords, a laptop charger, and debugging tools. Clean the space and hide tools — [Holson](https://generalrobots.substack.com/p/nailing-the-demo); also chargers, adapters, extension cords per [UCI BB Comp 2025](https://bbcomp.tech.uci.edu/wp-content/uploads/2025/05/BB-Comp-Showcase-Tips-and-Tricks-2025.pdf)
- Record a 60-second screen capture of the working flow as a Wi-Fi backup — [Kurbaitaev, dev.to](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l)
- Prepare a recorded video of the demo working, screenshots of key screens, and fallback material. If the live demo fails, switch calmly, since judges are more impressed by graceful recovery than rattled by a glitch — [Builderbase ch.14](https://intercom.help/builderbase/en/articles/14836128-builder-s-guide-ch-14-crafting-a-demo-that-lands)
- Search snippet from a demo guide: say you'll show a recorded demo while you fix the issue, explain what should have happened, and resume live if it recovers. Don't open the code editor or terminal, because judges care about the result. Another guide: if the prototype fails, show the partial result and explain the attempt instead of claiming success — snippets surfaced alongside [Builderbase ch.14](https://intercom.help/builderbase/en/articles/14836128-builder-s-guide-ch-14-crafting-a-demo-that-lands) and [positioniseverything hardware demo article](https://www.positioniseverything.net/how-to-document-and-demo-a-hardware-hackathon-project-so-judges-can-rebuild-it/) (exact wording not verified by fetch)
- QR codes on the table can link to a demo video (90 seconds or less if possible) and the live prototype interface. A looping video on a screen attracts passersby. Bring multiple prototype units for judge interaction — [UCI BB Comp 2025](https://bbcomp.tech.uci.edu/wp-content/uploads/2025/05/BB-Comp-Showcase-Tips-and-Tricks-2025.pdf)
- A multi-time winner reports that their event switched to videos after robot failures. Have a pre-recorded video ready if the rules allow — [John Kim, Push To Prod](https://getpushtoprod.substack.com/p/how-to-win-hackathons)
- A cautionary 2026 anecdote: a junior engineer tried an untested feature during a live robot demo for investors, the robot faceplanted, and recovery took 15 minutes — [The Register, "Who, Me?", Mar 2026](https://www.theregister.com/2026/03/23/who_me/) (snippet)
- MLH's hardware hackathon guide advises finding out whether judging is live, recorded, or asynchronous, and how many minutes you get — [MLH Hardware Hackathon Guide, Pitfalls](https://guide.mlh.com/hardware-hackathon-guide/pitfalls) (snippet)

### Inferences
- With science-fair judging, the same 3-minute demo repeats many times over 1-3 hours. Battery, thermal limits, and the camera's re-initialization between judges become reliability risks. A "reset to known state" routine (one command or button) between judges is probably as important as the demo itself.
- A "simulation/replay mode" counts as a legitimate fallback if it's labeled honestly. Example: replaying recorded camera frames through the same live pipeline when lighting or the camera fails. Say "this is replayed input through the live system" rather than letting a judge assume it's live, because judges penalize anything that reads as hiding (see Q5).
- Prepare a pre-written one-sentence failure line, for example "Hardware being hardware. Here's the same run recorded this morning while [Fixer] resets it." It should be the Talker's reflex, not something improvised.

### Gaps
- No quantitative data was found on how much a live failure costs in score versus a smoothly handled fallback. The claims are judge and practitioner impressions.
- The rules of this specific event on backup videos weren't checked. Confirm with organizers.

## Q4. How to make a technical property (real-time scheduling, crash recovery, fail-safe) visible and memorable in a live demo

### Takeaway
Abstract properties score only when judges see them, so stage a deliberate, controlled "break it" moment. Let the judge kill the process, overload the CPU, or pull a sensor while the system keeps working or recovers on screen. Pair it with a visible counter or indicator. For QNX, the High Availability Manager (HAM) plus `slay`/`kill` gives a documented, scriptable kill-and-restart scenario.

### Cited Findings
- Make the hardest feature you claim actually function on stage. "The one wow moment has to be real." — [John Kim, Push To Prod](https://getpushtoprod.substack.com/p/how-to-win-hackathons)
- Use props or physical models to make abstract ideas tangible. Let judges physically engage — [UCI BB Comp 2025](https://bbcomp.tech.uci.edu/wp-content/uploads/2025/05/BB-Comp-Showcase-Tips-and-Tricks-2025.pdf)
- Hack the North 2025's "WOW factor" criterion rates more favorably projects that show technical depth and advanced technical knowledge — [HTN 2025 judging criteria](https://hackthenorth.notion.site/2025-judging-criteria) (snippet only)
- QNX docs describe the High Availability Manager as a "smart watchdog." It can restart processes, wait between restarts for a process to be ready, and notify the process. Examples include simple restart, compound restart, and death/condition notification — [QNX 8.0 docs: Using the High Availability Framework](https://qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.prog/topic/process_High_Availability.html); [QNX 8.0 HAM "Simple restart" example](https://www.qnx.com/developers/docs/8.0/com.qnx.doc.ham/topic/examples_SIMPLE.html)
- HAM heartbeating: a HAM can automatically detect an unresponsive (not just dead) process and terminate it — [QNX 8.0 HAM heartbeat example](https://qnx.com/developers/docs/8.0/com.qnx.doc.ham/topic/examples_Process_heartbeat.html)
- `slay` kills or modifies a process by name or ID. `kill` sends SIGTERM by default — [QNX 8.0 slay](https://qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.utilities/topic/s/slay.html); [QNX 8.0 kill](https://qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.utilities/topic/k/kill.html)
- Industry precedent for "fault injection as a demo": Wind River shows a video in which a board goes offline and another board takes over its role — [Wind River blog, "Fault injection revisited with video"](https://windriver.com/blog/fault-injection-revisited-with-video) (snippet)

### Inferences (no direct source found; derived from the above)
- Pattern: claim, then break, then watch it hold. (1) Say the property in plain words ("the vision process can crash and the arm stays safe"). (2) Give the judge a big physical button, or let them type `slay <proc>`, so the judge causes the failure. (3) Show a large on-screen indicator, such as "restarts: 1, recovered in 180 ms, arm in safe-stop." (4) Repeat the one-line identity.
- Real-time scheduling is easier to see as a contrast. Run a CPU-hog stress process live and show that the control loop's jitter or deadline-miss counter stays flat. If you have a recorded non-RT baseline, show it next to the live run and label it as recorded.
- Fail-safe: physically block or cover the camera, or unplug a sensor, and show the robot entering a defined safe state (stops, LED turns red) instead of doing something random.
- Rehearse the fault injection as part of the 3x-in-a-row reliability test. A failed "recovery demo" is worse than no recovery demo.

### Gaps
- I found no hackathon-judge source that specifically discusses demoing RTOS or reliability properties. The pattern above is an inference.
- I found no public QNX-produced video of a live HAM kill-and-restart demo.

## Q5. Common Q&A questions for hardware/AI projects, how to answer them, and being honest about what's unfinished

### Takeaway
Expect questions in three groups: technical feasibility and edge cases, user desirability and impact, and viability or next steps. Also expect "what breaks first?" and "what did you build this weekend vs. before?" Answer in 1-3 sentences, name a specific known weakness out loud, and frame cuts as deliberate scope decisions only if they were.

### Cited Findings
- Three question types to prepare for: technical feasibility ("How does your AI model handle edge cases?"), user desirability ("Why does your customer/user want this?"), and market viability ("Could this sustain itself?"). Run mock sessions with engineering students as technical judges and people unfamiliar with the project — [UCI BB Comp 2025](https://bbcomp.tech.uci.edu/wp-content/uploads/2025/05/BB-Comp-Showcase-Tips-and-Tricks-2025.pdf)
- Brainstorm likely questions (scaling, target user, business model, differentiation, what you'd build next). Assign one teammate to technical questions and one to product questions. "We haven't figured that out yet, but our hypothesis is..." is an acceptable answer — [Builderbase ch.14](https://intercom.help/builderbase/en/articles/14836128-builder-s-guide-ch-14-crafting-a-demo-that-lands)
- Prepare an honest answer to "what breaks first?" Naming a specific known weakness raised scores, and claiming nothing breaks lost credibility. Be clear about what was built during the event versus what already existed, since blurring it "reads as hiding" — [Kurbaitaev, dev.to](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l)
- For missing features: "We scoped that out intentionally to focus on the core experience," but only if it was actually intentional. Missing features can become roadmap items — [John Kim, Push To Prod](https://getpushtoprod.substack.com/p/how-to-win-hackathons)
- If the prototype isn't fully functional, clearly explain what works and what's next — [UCI BB Comp 2025](https://bbcomp.tech.uci.edu/wp-content/uploads/2025/05/BB-Comp-Showcase-Tips-and-Tricks-2025.pdf)
- Search snippets: judges probe whether you understand your code ("Don't let AI build everything without understanding it"), and a hackathon veteran notes no judge question should take more than a few sentences to answer — [DEV, "Hackathon survival guide: questions every team should be ready to answer"](https://dev.to/techie_sprinter/hackathon-survival-guide-questions-every-team-should-be-ready-to-answer-bcd); [Gleb Bahmutov, "Winning hackathons"](https://glebbahmutov.com/blog/winning-hackathons/) (snippets, not fetched)
- MLH advises judges that they may ask questions to clarify any part of a project, and to favor learning over profit — [MLH Judging Plan](https://guide.mlh.com/general-information/judging-and-submissions/judging-plan)

### Inferences
- Likely questions for a QNX/robotics/vision project, with answers to pre-write in one or two sentences each:
  - "Why QNX / why an RTOS instead of Linux?" Give a concrete reason tied to what was shown (determinism, process isolation, restart).
  - "What happens if the camera or model is wrong?" Name the fail-safe behavior you showed.
  - "What's actually running on the Pi vs. your laptop?" Be precise. This is the "built vs. pre-existing" honesty test.
  - "What breaks first?" Give one specific weakness (lighting, latency, grip reliability).
  - "What would you do with more time?" Give one or two concrete next steps.
  - "How accurate / how fast?" Have one real measured number.
  - Health-track judges: "Who is the user, and is it safe?"
- With only 1 minute, aim for about 3 short answers. End each answer by pointing back to the hardware ("you can see that here").

### Gaps
- No source gave a statistically grounded list of the most-asked questions. The lists are compiled from guides.

## Q6. How judges score against criteria (Innovation, Technical Complexity, Completeness, Design), and tailoring to sponsor, health-track, and general judges

### Takeaway
Rubrics typically have 4-5 weighted criteria on 1-5 or 1-10 scales. Many science-fair events actually stack-rank, with each judge picking a top 3. Most teams land mid-range on every criterion, so winners are separated by clarity, a working end-to-end demo, a memorable identity, and honesty. Sponsor judges reward deep, visible use of their technology and "the thing they wanted to exist." Specialist category prizes are often judged by 1-2 subject-matter experts.

### Cited Findings
- Typical rubric: 4-5 criteria, 1-5 or 1-10 scale, sometimes weighted. Example weights: Innovation/Creativity 25%, Technical Execution 25% (a working prototype with suitable tech), Impact/Usefulness 20%, Presentation 15%, Design/UX 15%. Panels differ: investors favor viability, engineers technical depth, designers UX. Mention the sponsor's tool in the demo for sponsor categories — [Builderbase ch.15, How judging works](https://intercom.help/builderbase/en/articles/14836129-builder-s-guide-ch-15-how-judging-works)
- UCI BB Comp 2025 weights: Idea 20%, Design (technical architecture) 30%, Demo (working prototype quality) 40%, Presentation 10% — [UCI BB Comp 2025](https://bbcomp.tech.uci.edu/wp-content/uploads/2025/05/BB-Comp-Showcase-Tips-and-Tricks-2025.pdf)
- Another published rubric: Technical 40%, Idea 30%, Design 20%, Wow factor 10% — [Global Travel Hackathon evaluation criteria (GitHub)](https://github.com/Global-Travel-Hackathon/Evaluation-Criteria) (snippet)
- Rubrics commonly cover technical difficulty, originality, design, impact, and sponsor API use. Most teams score mid-range, so the deciding factors aren't named in the rubric. Polish beyond legibility, framework choice, and team credentials did not move scores. One narrow thing built well beats a broad platform — [Kurbaitaev, dev.to](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l)
- MLH science-fair judging: each judge reports a top 3 (3/2/1 points), and points are summed. Stack ranking normalizes harsh vs. generous judges. For small categories like AI or Hardware, 1-2 subject-matter experts judge only those projects — [MLH Judging Plan](https://guide.mlh.com/general-information/judging-and-submissions/judging-plan)
- Sponsors are in the room and effectively act as judges, and they want to hear their products named. Talk to them early, and treat their enthusiasm or lukewarm reaction as a signal. The Esri sponsor at TechCrunch Disrupt gave the prize because the team "built what he wanted to exist" — [John Kim, Push To Prod](https://getpushtoprod.substack.com/p/how-to-win-hackathons)
- "Focus on deep integrations" for sponsor prizes — [Cloudinary, dev.to "How to win a hackathon"](https://dev.to/cloudinary/how-to-win-a-hackathon-1377) (snippet)
- Organizer guide: sponsorship is a marketing line item for the vendor, and judges should be briefed on each sponsor's criteria — [Deepak Gupta, Hackathon sponsorship guide](https://guptadeepak.com/hackathon-sponsorship-guide/) (snippet)
- UCI: be flexible if judges want to dive deeper, and adjust the pitch to the audience's background and interests — [UCI BB Comp 2025](https://bbcomp.tech.uci.edu/wp-content/uploads/2025/05/BB-Comp-Showcase-Tips-and-Tricks-2025.pdf)

### Inferences: tailoring the same 3-minute demo
- Keep the demo path identical and swap only three things: the opening hook sentence, which "wow" moment gets the extra 20 seconds, and the closing line. Ask in the first 5 seconds "Which track are you judging?" or read their badge.
- **Sponsor judge (e.g., QNX):** Name QNX in the first sentence. Spend the wow time on the crash-recovery or real-time moment (HAM restart, deadline counter under load). Be precise about which QNX features or APIs you used and what ran on QNX versus elsewhere. Frame it as "the thing QNX wants to exist," for example a showcase for safety-critical robotics on QNX.
- **Health-track judge:** Open with a specific patient or caregiver and the harm avoided. Spend the wow time on the fail-safe (it stops safely when uncertain). Mention safety, the human in the loop, and a realistic deployment setting. Keep RTOS jargon to one sentence ("guaranteed response time").
- **General judges:** Lead with the one-line identity and the most visual moment. Cover one tech sentence that maps to "technical complexity," one honest limitation, and a memorable closing line. Make sure each rubric criterion is touched at least once (innovation: what's new; technical: the hard part working live; completeness: end-to-end; design: the physical and UI experience).
- Because of MLH-style stack ranking, the goal is to be one judge's top-3 pick, which comes from being memorable and distinct, not from being merely solid on every axis.

### Gaps
- No official 2025/2026 Hack the North or Hack Western rubric text could be retrieved; only the HTN "WOW factor" snippet. Check this event's published rubric and sponsor prize criteria directly.
- No source specifically covers health-track judging criteria at student hackathons.
