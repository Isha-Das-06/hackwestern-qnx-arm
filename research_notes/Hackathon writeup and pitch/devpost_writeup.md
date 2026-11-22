# Writing a winning Devpost "About the project" write-up

Method note: Devpost pages block the WebFetch tool (HTTP 403), so on 2026-11-22 I pulled the public HTML with curl. I took the winner lists from each hackathon gallery's `challenge-winners-json-ld` block and measured word counts and sections with a script. The script counted only the text inside `#app-details-left` and did not include "Built with". "Video" means a YouTube or Vimeo embed appears on the page. All counts are approximate.

## 1. What judges and organizers say they look for, and how much time they spend

### Takeaway
Judges spend roughly 2 to 5 minutes per project, and at in-person events most of that time goes to the live demo. The write-up has to be easy to skim. Put the problem and what makes the project stand out in the first two paragraphs, keep Devpost's template headings, follow the published criteria, and make sponsor-specific details easy to find.

### Cited Findings
- MLH's organizer guide recommends science-fair judging: teams stay at numbered tables and judges walk around. Its judge-time formula is 4 minutes per project (2 for presentation and demo, 1 for questions and scoring, 1 for walking between tables). Elsewhere the same guide says judges get "only 3 minutes per team". Each project should be seen by 3 judges. Winners are chosen by stack ranking: each judge picks a top 3, worth 3, 2 and 1 points. — [MLH Organizer Guide: Judging Plan](https://guide.mlh.com/general-information/judging-and-submissions/judging-plan.md)
- MLH recommends that each team submit a 2-minute demo video showing the hack itself, not a presentation. At science-fair events the videos are used in final deliberations. The guide also recommends that small categories such as hardware be judged by one or two subject experts, and that organizers run a cheating check on all winners. — [MLH Organizer Guide: Judging Plan](https://guide.mlh.com/general-information/judging-and-submissions/judging-plan.md); [MLH guide (search snippet)](https://guide.mlh.io/general-information/judging-and-submissions/judging-plan)
- Jacklyn Biggin (MLH Coach, judge at about 20 digital hackathons; 2021, edited 2023) says judges often have about 5 minutes per project, so the key information should come first. Her other points:
  - Keep Devpost's template headings; teams that delete them tend to leave out key details.
  - Read the public judging criteria and write to it.
  - For sponsor prizes, say which product you used, why, and what it does in your project, and make that easy to find.
  - Start the write-up by Saturday evening; incomplete Sunday-morning submissions are the classic failure. — [DEV: How to make your Devpost submissions not suck](https://dev.to/jacklynbiggin/how-to-make-your-devpost-submissions-not-suck-37i0)
- DoraHacks says a judge who reads only the first two paragraphs should already understand what makes the project worth attention. It suggests answering four questions directly: the problem, why it matters, who it's for, and how it works. It warns against "grandiose" claims and vague marketing language, and says to give sponsor integrations their own section and state eligibility explicitly. — [DEV/DoraHacks: What does a good hackathon submission look like?](https://dev.to/dorahacks/what-does-a-good-hackathon-submission-look-like-5398)
- Magomed Kurbaitaev wrote up a year of judging (events in 2026). His observations:
  - Narrow, finished projects scored higher ("one narrow thing well reads as a team that made decisions").
  - Open with a plain sentence of the form "this is a tool that does X for Y".
  - Specific audiences signal real research ("a regional fighter with 40,000 followers and no manager" rather than "athletes").
  - Naming a known weakness before being asked raised scores.
  - Being vague about what was built at the event "reads as hiding". — [DEV: What judges actually score](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l)
- Amit Kumar Singh judged a batch of AI and developer projects (2026). He found that "some technically strong projects were harder to evaluate because the documentation was thin". He lists what helps: a README, an architecture diagram, a demo video, screenshots, setup steps and known limitations. — [DEV: What I learned after reviewing many AI and developer projects as a hackathon judge](https://dev.to/amising6/what-i-learned-after-reviewing-many-ai-and-developer-projects-as-a-hackathon-judge-2g06)
- MLH's standard rules weight technology, design, completion and learning equally. — cited in [Position Is Everything: hardware hackathon documentation (Nov 2026)](https://www.positioniseverything.net/how-to-document-and-demo-a-hardware-hackathon-project-so-judges-can-rebuild-it/). I did not check this against the primary MLH rules page.
- A JetBrains post from June 2026 that interviewed judges reportedly found that every judge said some version of "start with the problem". This comes from a search snippet only, because the page returned 403. — [JetBrains: Notes from the judging table](https://blog.jetbrains.com/ai/2026/06/how-to-win-a-hackathon-notes-from-the-judging-table/)
- In a Bolt judge spotlight, the CEO of Pica says he looks for clarity of purpose, thoughtful execution and usefulness, with design taste as a bonus. This is from a search snippet. — [Bolt: Hackathon Judge Spotlight](https://bolt.new/blog/hackathon-judge-spotlight)

### Inferences
- At in-person Canadian events (Hack the North, nwHacks, MakeUofT) the expo demo decides most of the result. The write-up still matters in three places: the finalist shortlist, sponsor judges who read Devpost before or after visiting tables, and the post-event cheating and eligibility check. Write it so a sponsor judge can confirm eligibility in under 30 seconds.
- Expect a skim, not a full read. The top media item and the first two sentences carry most of the weight.

### Gaps
- I found no official Devpost help-center article with length guidance. Devpost's own blog posts did not come up in searches, and Devpost blocks the fetch tool.
- I found no measured data on how long judges spend reading the text as opposed to watching the demo.

## 2. Length, technical depth, numbers, equations and tables

### Takeaway
Thirteen winning hardware write-ups ran 418 to 955 words, with a median of about 560. They are moderately technical: named parts, what each part does, and the data path. Hard numbers are rare, and none used tables, code blocks or equations. A few well-chosen measured numbers would make a write-up stand out, but a page full of maths would be out of character for the genre.

### Cited Findings: sample of real winners (word counts from my scrape)
| Project (event, prize) | Words | Video embed | Notes |
|---|---|---|---|
| [QNX-RasPi-Setup-Util](https://devpost.com/software/qnx-raspi-setup-util) (HTN 2025, **QNX: Best Use of QNX**) | 443 | no | Standard 7 headings. Solo author. Names the stack: C++, CMake, QNX SDP 8.0, QNX Toolkit, Docker build env, FTXUI. Challenge described plainly (QNX toolchain setup "took me a relatively long time"). "What's next" is the longest section (122 words). |
| [QNXMobility](https://devpost.com/software/canqnx) (HTN 2025, **QNX: Best Use of QNX**) | 506 | no | Swerve-drive chair steered by an IMU (lean to move). Mechanical detail: 3D-printed housings, CNC aluminium plates, ODrive FOC controllers, QNX Pi kit. Honest challenge: "Interfacing this machine with QNX was also a challenge as it didn't natively have libraries". **The "What's next" section is left as the template heading "What's next for Untitled" with 1 word, and it still won.** |
| [DUM-E](https://devpost.com/software/dum-e-kgx6at) (HTN 2025 Finalist) | 830 | yes | LLM + CV robot arm. Explains the design choice ("Initially, we thought of using VLAs... Thus, we designed our own pipeline"). Numbered pipeline steps. Concrete electrical numbers in Challenges: large servos up to 2 A, small 1 A, "9A of current running in total". |
| [ROSS](https://devpost.com/software/ross-42pnvi) (HTN 2025 Finalist) | 845 | yes | Tactile art for blind users. 7 captioned images (CAD, wiring, edge extraction, stroke graphs). BOM-style detail: 2 NEMA steppers, servos, Arduino, a 10 ohm resistor as heated brush. "How we built it" is the longest section (319 words). |
| [ChessMate](https://devpost.com/software/chessmate-nwygvq) (HTN 2025 Finalist) | 462 | yes | Emoji headings. Parts named: 2x NEMA 17, DRV8825, Raspberry Pi 5, Arduino, electromagnet. 9 images. |
| [PulseGrip](https://devpost.com/software/pulsegrip) (HTN 2024 Finalist) | 669 | yes | Merged "What it does and how we built it". Candid challenges: "we fried our EMG sensor, twice!", pivoted to an ECG sensor, websocket debugging. |
| [Spyder](https://devpost.com/software/spyder) (HTN 2023 Finalist + Viam prize) | 955 | yes | BCI-driven kiddie car. "How we built it" split into Mechanical, Electrical and Software (388 words). Humour and honesty: "it only caught fire once - which we consider to be a personal best". Admits the BCI "didn't always work". |
| [RoBotany](https://devpost.com/software/the-plant-whisperer) (HTN 2023 Finalist + BentoML) | 781 | yes | Build section has Hardware, Frontend and Backend subheads. Long challenges section (189 words). |
| [RxID](https://devpost.com/software/rxid) (MakeUofT 2025, **1st Place**) | 564 | yes | Health track: RFID bracelet plus pill dispenser. Tightly problem-led ("reducing medication errors"). |
| [The Quicker Picker Upper](https://devpost.com/software/the-quicker-picker-upper) (MakeUofT 2025, 2nd) | 461 | yes | Custom headings in one block. Honest power challenge: four servos run from the Pi caused "power instability", fixed with an external supply. |
| [PrimePong](https://devpost.com/software/primepong) (MakeUofT 2025, 3rd) | 473 | yes | Playful inspiration about a teammate. Parts named: ESP32, ESP8266, MPU6050, force sensor. Admits one force sensor "stopped being responsive". |
| [LLM-navigated robots for life amid ashes](https://devpost.com/software/controlling-robots-with-llms-through-smoke) (nwHacks 2025, Team Choice) | 418 | yes | Jetson Nano JetBot. Explains a design pivot from the OpenAI API to a local Llama 3.2-vision 11B on an RTX 3070, because connectivity in a disaster zone can't be assumed. |
| [scaNFT](https://devpost.com/software/scanft) (HTN 2021, Raspberry Pi says it won) | 697 | yes | Pi 4 turntable that takes about 50 photos per scan. Added custom sections ("How to use", "Technical Workflow"). — [Raspberry Pi news](https://www.raspberrypi.com/news/raspberry-pi-project-wins-north-americas-largest-hackathon/) |

- Winner lists come from the galleries ([HTN 2023](https://hackthenorth2023.devpost.com/project-gallery), [HTN 2024](https://hackthenorth2024.devpost.com/project-gallery), [HTN 2025](https://hackthenorth2025.devpost.com/project-gallery), [nwHacks 2024](https://nwhacks-2024.devpost.com/project-gallery), [nwHacks 2025](https://nwhacks-2025.devpost.com/project-gallery), [MakeUofT 2025](https://makeuoft-2025.devpost.com/project-gallery)). The Hack Western 11 and UofTHacks 12 gallery subdomains I guessed returned empty pages, so those events are not covered.
- My script found no `<table>`, `<pre>` or `<code>` blocks in any of the 13 write-ups. Numbers with units were rare: 0 to 3 per page.
- DoraHacks says specific details, such as naming each component and what it outputs, build credibility. — [DoraHacks](https://dev.to/dorahacks/what-does-a-good-hackathon-submission-look-like-5398)
- The hardware documentation guide (Nov 2026) says to name the conditions that affect results (lighting, distance, network, warm-up, battery). In the demo, it says to explain one technical decision tied to a constraint such as latency, power or noise, and to show a visible or measurable output. — [Position Is Everything](https://www.positioniseverything.net/how-to-document-and-demo-a-hardware-hackathon-project-so-judges-can-rebuild-it/)

### Inferences
- A target of about 500 to 900 words fits the winners. Going much past 1,000 words is outside the norm and works against the 3 to 5 minute skim.
- "How we built it" is usually the longest section in hardware winners (235 to 388 words in DUM-E, ROSS, Spyder and RoBotany). Splitting it into Hardware, Software and Mechanical subheads, or a numbered pipeline, is a common pattern.
- Real-time sponsors such as QNX are likely to value measured numbers: loop period, jitter, latency, deadline misses. Because winners almost never include them, one or two measured figures with their measurement method would set a write-up apart. This is an inference; no source says judges reward benchmarks specifically.
- A single small table (for example, measured latency per stage) is probably fine. Equations would look out of place in the genre; a link to the repo is the better home for them. Inference only: no source tested this.

### Gaps
- No source directly says whether equations or tables help or hurt judging.
- Sample size is 13 and leans toward Hack the North. Word counts depend on how my script parsed the pages.

## 3. Patterns in winning hardware and robotics write-ups (media, honesty, structure)

### Takeaway
Winners keep Devpost's seven headings, sometimes merging or adding sections. They open with a short human-scale inspiration, list named parts and the signal path, and write the Challenges section with concrete, often funny, honesty (fried sensors, fires, power brownouts, pivots). A photo gallery and a YouTube demo come first.

### Cited Findings
- 11 of the 13 sampled winners embed a YouTube demo. The two exceptions are both HTN 2025 QNX prize winners, which may reflect sponsor judges evaluating in person. Every winner has a photo gallery; ROSS, PulseGrip and ChessMate have 7 to 9 captioned images (CAD, wiring, team photo, the device in use). — scraped pages linked in the table above
- Candid failure stories appear in winning write-ups, for example PulseGrip ("we fried our EMG sensor, twice!"), [Spyder](https://devpost.com/software/spyder) ("it only caught fire once"), [Quicker Picker Upper](https://devpost.com/software/the-quicker-picker-upper) (servo power instability) and [PrimePong](https://devpost.com/software/primepong) (a sensor died). — [PulseGrip](https://devpost.com/software/pulsegrip)
- Hardware documentation advice:
  - Use a well-lit photo of the assembled prototype as the cover, not a breadboard, CAD render or stock image.
  - Take build-stage photos, including one showing cable routing and one close-up with readable labels.
  - Include a legible wiring diagram whose pin names match the code, and a BOM with exact part models.
  - Keep working and planned features separate, and never describe planned features in the present tense.
  - If hardware fails at judging, show the working subsystem and logs.
  - The same guide reports event-specific scoring: at HackMIT26 x Hackster, documentation is worth 25 of 100 points; in a Hackster Arduino UNO Q contest it is worth 30, with the BOM 20 and schematics 15. — [Position Is Everything (Nov 2026)](https://www.positioniseverything.net/how-to-document-and-demo-a-hardware-hackathon-project-so-judges-can-rebuild-it/)
- Kurbaitaev advises getting one end-to-end path working by the halfway mark, cutting the rest, and describing unbuilt parts in one sentence. He also suggests recording a 60-second screen capture as a fallback, because "Wifi fails at most events I judged". — [Kurbaitaev](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l)
- Biggin recommends splitting the demo video work across people: one writes the script, one records the screen, one records the voiceover. — [Biggin](https://dev.to/jacklynbiggin/how-to-make-your-devpost-submissions-not-suck-37i0)

### Inferences
- A recommended order: hero photo of the real device, then the 2-minute demo video, then a one-sentence "X for Y" opening in Inspiration. After that come named parts and a data-flow description, then candid Challenges with the fix for each, and a clear line between working and next. Close with the repo link.
- Short GIFs of motion (an arm moving, a wheel responding to a lean) are a natural fit for the gallery. None of the sources measured GIFs specifically.

### Gaps
- I found no data comparing win rates with and without video. The 11 of 13 figure is descriptive only.

## 4. Covering several sponsor prizes (e.g., a QNX real-time track plus a health track) without diluting the story

### Takeaway
Keep one main story: problem, user, demo. Then make each prize's evidence explicit and easy to scan, for example with a short labelled paragraph per sponsor that says what you used, why, and what it does. Sponsor judges search for their product, and many winners take two or three prizes with one coherent project.

### Cited Findings
- For sponsor categories, say which products you used, why, and what they do in your project, and make these easy to find. A judge looking for a specific item may give up if it is not obvious. — [Biggin](https://dev.to/jacklynbiggin/how-to-make-your-devpost-submissions-not-suck-37i0)
- Give sponsor integrations their own section and state eligibility explicitly rather than expecting judges to dig through the code. — [DoraHacks](https://dev.to/dorahacks/what-does-a-good-hackathon-submission-look-like-5398)
- Cloudinary's advice is to focus on deep integrations for sponsor prizes. From a search snippet. — [DEV/Cloudinary: How to win a hackathon](https://dev.to/cloudinary/how-to-win-a-hackathon-1377)
- Multi-prize winners from one project include Spyder (finalist plus Viam), RoBotany (finalist plus BentoML), PathSense (HTN 2024 finalist plus Cohere), excus.us (Convex, Cohere and Web Summit) and Battle Over Bins (MakeUofT 2025 Sustainability theme plus .Tech). — [HTN 2023](https://hackthenorth2023.devpost.com/project-gallery), [HTN 2024](https://hackthenorth2024.devpost.com/project-gallery), [MakeUofT 2025](https://makeuoft-2025.devpost.com/project-gallery) winner JSON-LD
- The HTN 2025 QNX prize text: QNX awards one prize for the best QNX + hardware project and one for the best QNX + software-only project. Its prompts include "Can you make something that moves and accomplishes a goal?", "prototype an industrial control system", and "a hardware solution to a real-world problem". — [Hack the North 2025 Devpost](https://hackthenorth2025.devpost.com/)
- MLH suggests judging small categories such as hardware with one or two subject experts. In practice that means a technically literate sponsor engineer reading the QNX evidence. — [MLH Judging Plan](https://guide.mlh.com/general-information/judging-and-submissions/judging-plan.md)

### Inferences
- In a combined QNX-plus-health project, the health problem and its user can be the story in Inspiration and What it does. The QNX real-time evidence then goes in a clearly labelled part of How we built it, for example "Why QNX / real-time". Name the specific QNX features used, such as process isolation, priorities, timers or message passing, and why a health device needs determinism. Give the measured timing.
- Avoid restating every sponsor in every section. One labelled paragraph per prize, plus the prize names in "Built with", is enough.
- Both HTN 2025 QNX winners were plain, roughly 450 to 500 word write-ups whose main QNX point was "we got QNX working with real hardware or tooling". That suggests the bar is clear evidence of real QNX use, not polish.

### Gaps
- I found no published QNX judging rubric beyond the prize prompts.

## 5. Sounding authentic, not AI-generated

### Takeaway
No source gives a rule for detecting AI-written text. The guidance that exists points one way: say specifically what you built and how (and how AI tools helped), use your own voice, avoid inflated claims, and keep concrete, slightly messy details from the build.

### Cited Findings
- The stronger submissions were honest about how AI helped, naming uses such as "boilerplate, debugging, refactoring, documentation, test cases". They "did not claim that AI magically built the entire project". — [Singh](https://dev.to/amising6/what-i-learned-after-reviewing-many-ai-and-developer-projects-as-a-hackathon-judge-2g06)
- Being vague about what was built during the event "reads as hiding". Specific audience details signal real research. — [Kurbaitaev](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l)
- Avoid "grandiose" claims; whether something is "revolutionary" is for judges to decide. Don't bury the key innovation under vague marketing language. — [DoraHacks](https://dev.to/dorahacks/what-does-a-good-hackathon-submission-look-like-5398)
- A judge's post (via search snippet) says polished output from AI builders can look AI-generated, and that a presenter's own voice tends to land better than an AI voiceover. Devfolio's guidelines prohibit text-to-speech narration in walkthrough videos. — search results for [Devfolio judging guide](https://guide.devfolio.co/docs/guide/participating-in-hackathons/judging-1); the judge's post was not fetched
- Winning hardware write-ups read as human: first-person asides ("took me a relatively long time"), named teammates and jokes (PrimePong's "Stefan"), self-deprecating failures (Spyder's fire), and some typos (scaNFT writes "RasberryPi"). — [QNX-RasPi-Setup-Util](https://devpost.com/software/qnx-raspi-setup-util), [PrimePong](https://devpost.com/software/primepong), [Spyder](https://devpost.com/software/spyder), [scaNFT](https://devpost.com/software/scanft)

### Inferences
- These patterns tend to read as machine-written, and the human winners above don't use them: every section the same length; stock phrases ("seamless", "revolutionize", "empower", "cutting-edge", "in today's fast-paced world"); rule-of-three adjective lists; "not just X, but Y" constructions; long em-dash runs; and challenges without a concrete fix or number. RxID and ROSS use some of these phrases ("seamless", "seamless demo") and still won, so this is a credibility risk, not a disqualifier.
- Specifics that only the team could know read as authentic: the part that burned out, the value you tuned, the time something took, a photo of the messy bench.
- Do not invent numbers. Report only what you measured and say how you measured it (this also follows the "separate working from planned" advice).

### Gaps
- I found no survey or organizer policy that quantifies judges penalising AI-written Devpost text. The Devfolio AI-judging blog posts appeared in search but were not fetched.
