# QNX judging priorities and health framing for an assistive pick-and-place arm

Researched 2026-11-22. About 20 tool calls. Some primary pages could not be opened: oss.qnx.com renders its package list client-side, a StatCan page returned 403, and DeepWiki returned 429. These are flagged inline.

## (a) What are QNX's open-source AI modules on oss.qnx.com, and what exact names should we cite?

### Takeaway
oss.qnx.com is QNX's package dashboard for open-source software ported to QNX ("Explore open source software that has been ported to work on QNX"). It lists 876 projects, 2,879 packages and 14,701 builds. TensorFlow Lite has a QNX port with a Python `tflite_runtime` for QNX 7.1/8.0 on aarch64le. I could not get the dashboard to show a TFLite entry by name, and QNX's own 2026 blog lists TFLite only through its dependencies (XNNPACK, ruy, FlatBuffers). Hand tracking appears as a pre-built graph inside the MediaPipe port, which QNX calls "in-flight", cross-compile only. There is no standalone hand-tracking package. The safest citation is "TensorFlow Lite (tflite_runtime) from QNX's open-source ports (oss.qnx.com / qnx-ports), with the hand-tracking pipeline ported from the QNX AI workshop / MediaPipe hand-tracking sample."

### Cited Findings
- oss.qnx.com landing page: titled "Package Overview", described as open-source software ported to work on QNX, with counts of 876 projects, 2,879 packages and 14,701 builds. The listing is rendered dynamically and did not show up in a text fetch. — [oss.qnx.com](https://oss.qnx.com)
- QNX's 2026 blog "How QNX Gives Developers the Building Blocks for Physical AI" splits packages into two groups. One is APK-packaged in aports/extra and buildable natively with QDD. The other is "cross-compile only": builds are validated but not yet APK-packaged. The post tells readers to check oss.qnx.com for current status. — [QNX blog](https://qnx.software/en/blog/2026/how-qnx-gives-developers-the-building-blocks-for-physical-ai)
- That same post says:
  - TFLite is not its own entry. It appears through its dependencies: XNNPACK (inference backend), ruy (CPU matrix backend), FlatBuffers (model format) and Google's cpu_features library.
  - onnxruntime, OpenCV 4.9, PyTorch, OpenVINO, XLA, NumPy, protobuf, gRPC, libcamera and zenoh are cross-compile only.
  - MediaPipe is cross-compile only and "in-flight", with pre-built graphs for hand tracking, pose estimation, face mesh and object detection.
  - JAX, Eigen, Ceres Solver, FFTW and FlatBuffers are APK-packaged.
  - Its theme line: "QNX is enabling people to make their robots smart." — [QNX blog](https://qnx.software/en/blog/2026/how-qnx-gives-developers-the-building-blocks-for-physical-ai)
- The qnx-ports `build-files` TensorFlow Lite port is built with CMake and supports QNX 7.1 and 8.0 on aarch64le and x86_64. It includes a Python runtime, `tflite_runtime`, for inference without full TensorFlow. It needs NumPy first, and Python 3.11 on host and target. This comes from a DeepWiki mirror of the README, which is a secondary source; a direct fetch hit a rate limit. — [DeepWiki: qnx-ports/build-files 6.2 tensorflow-lite](https://deepwiki.com/qnx-ports/build-files/6.2-tensorflow-lite)
- The QNX hackathon resource page (Hack the 6ix) points to codelabs for "MediaPipe (C++ only), Claude Code, and llama.cpp", plus Gemini REST examples (`ai-services-rest-examples` on GitLab). — [QNX @ Hack the 6ix](https://devblog.qnx.com/ht6/)
- QNX's SDP 8.0 Raspberry Pi image ships "many available open-source sample apps, ports, and utilities" and links to an open-source ports section. — [QNX Everywhere docs](https://www.qnx.com/developers/docs/qnxeverywhere/com.qnx.doc.qnxeverywhere/topic/introduction.html)
- A prior QNX hackathon project, Scribly, ran hand tracking on QNX on a Raspberry Pi 4 using OpenCV and MediaPipe Hands in Python, not TFLite. — [Devpost: Scribly](https://devpost.com/software/scribly)

### Inferences
- The track requires "an open-source AI module from oss.qnx.com". The strongest defensible claim is: "We run Google's TensorFlow Lite via the QNX-ported `tflite_runtime` Python package (qnx-ports / oss.qnx.com), executing the MediaPipe palm-detection and hand-landmark TFLite models from the QNX AI workshop on the Pi." Before submitting, the team should check the exact package name and version on the device, for example from their install log or `pip show` / `apk info` output. Judges may ask.
- The MediaPipe port is C++ only and still in-flight. A Python port of the hand tracker running on `tflite_runtime` is a real contribution worth saying out loud: "we made the workshop's hand tracker run in Python on QNX 8.0 using the ported TFLite runtime."
- Use QNX's own phrase "physical AI" in the pitch. It is their current framing for AI on robots.

### Gaps
- I could not confirm that oss.qnx.com lists a package literally named `tflite-runtime` or `tensorflow-lite`, because the dashboard search renders client-side. Check in a browser or on the device.
- I did not find a public page for the "QNX AI workshop hand tracker" sample, so I can't give its exact repo name.

## (b) What did past QNX hackathon winners emphasise?

### Takeaway
QNX's published recaps reward four things. The first is real use of RTOS features: C, multithreading, thread priorities, multiple sensors on one bus. The second is technical grit: solving hurdles without sample code, and pivoting. The third is completeness: end-to-end polish, architecture docs, even a commercialization plan. The fourth is projects that expose QNX's process model, such as a remote process monitor. Assistive and safety-themed projects (for vision-impaired users, search and rescue, driver drowsiness) show up often among QNX submissions.

### Cited Findings
- Hack the 6ix 2025: QNX ran a "Best Use of QNX" prize and received more than 15 submissions. — [QNX blog: Hack the 6ix 2025](https://qnx.software/en/blog/2026/hack-the-6ix-2025)
  - The winner was Beats By Air, an air-drum kit built from I2C motion sensors on sticks. It is written in C, uses multithreading and thread priorities, and reads multiple sensors on a single I2C bus.
  - QNX credited the team for attending the QNX workshop, making "good use of QNX real-time operating system features", and working through complex samples with little help.
  - Other QNX-track projects that won event prizes: Fridge Mind (camera plus AI), IntelliDrive (an LLM and camera rover) and 6ixenality.
  - Notable submissions included Solari (describes surroundings to vision-impaired users), SAGE (a search-and-rescue aid drop), wakeruper (driver drowsiness) and FightStance (MediaPipe pose).
  - QNX quotes: "A positive QNX community experience is so important to us" and "Using QNX for a weekend project is absolutely possible."
- cuHacking 6: — [QNX blog: cuHacking 6](https://qnx.software/en/blog/2026/qnx-at-cuhacking-6)
  - Hardware 1st place, QNXFighter (QNX Screen API plus GPIO), was praised for "technical aptitude and resilience in pivoting".
  - Hardware runner-up, Plantr (a sensor with an AI back end), was praised for solving hurdles with no available sample code and for a "sense of completeness", including a commercialization strategy.
  - Software 1st place, QNXtainer, was "very complete end-to-end", and judges highlighted its architecture documentation.
  - Software runner-up, RPM (Remote Process Monitor), shows process states, flags resource anomalies and suspends processes. Judges called it "well polished and completed".
- QNX has also run or judged the first QNX Everywhere hackathon in India (winner: Team Agnisense) and events at CMU, uOttaHack, Hack the North and YHack. A QNX Global Hackathon 2026 has a submission deadline of 15 December 2026. — [QNX blog: India hackathon](https://qnx.software/en/blog/2026/judging-the-first-qnx-everywhere-hackathon-in-india); [QNX @ Hack the North](https://devblog.qnx.com/htn); [Internshala listing](https://internshala.com/competitions/?p=13426)

### Inferences
- The project maps well onto what QNX praised before:
  - The real-time gripper loop parallels Beats By Air's thread priorities, and adds a measured result: 0.49 ms versus 137 ms worst-case lateness.
  - The supervisor that restarts crashed processes parallels RPM's process-level view, and goes further with automatic recovery.
  - The Python TFLite port parallels "no sample code, solved it anyway".
- Bring numbers and an architecture diagram, and show a live fault-injection demo: kill a process mid-grip and the arm still holds. QNX judges explicitly praised architecture documentation and end-to-end completeness.
- A short "path to product" slide (cost, who buys it) echoes Plantr's commercialization praise and also serves the Sun Life prize.

### Gaps
- I found no QNX-published recap of Hack Western 11 or 12 QNX winners, and no recap of Hack Canada. No formal QNX judging rubric was published in the recaps I read.

## (c) What vocabulary does QNX use about safety-critical and real-time systems?

### Takeaway
QNX's product pages lean on these terms:
- "safe-by-design microkernel architecture"
- "spatial and temporal isolation" (defending against "internal faults and external threats")
- "deterministic behavior" and "real-time determinism"
- "real-time responsiveness"
- priority-based scheduling with adaptive time partitioning
- third-party certification: TÜV Rheinland, ISO 26262 ASIL D, IEC 61508 SIL 3, and IEC 62304 Class C (medical device software), with "surgical robot" given as an example application

IEC 62304 is the hook that ties QNX to a health pitch.

### Cited Findings
- QNX OS for Safety 8.0 is certified by TÜV Rheinland to ISO 26262 ASIL D, IEC 61508 SIL3, IEC 62304 Class C and ISO/SAE 21434. The page uses the phrases "safe-by-design microkernel architecture", "spatial and temporal isolation", "deterministic behavior" and "real-time responsiveness", and lists "surgical robot" as an example product. — [QNX OS and OS for Safety 8.0](https://qnx.software/en/software/products-and-solutions/qnx-os-and-os-for-safety)
- QOS 8.0 is a certified Safety Element out of Context (SEooC) with qualified C/C++ toolchains (ISO 26262 TCL3 / IEC 61508 TL3). It is built on a "next-generation microkernel" and offers more real-time determinism than prior releases. — [Embedded Computing Design: QNX launches QOS 8.0](https://embeddedcomputing.com/technology/software-and-os/os-filesystems-libraries/qnx-launches-qnx-os-for-safety-qos-80-for-safety-and-security-critical-embedded-systems); [Newswire release](https://www.newswire.com/news/qnx-launches-qnx-os-for-safety-qos-8-0-to-accelerate-development-of-safety-and)
- The QNX robotics solution guide, as summarised in search results, says priority-based scheduling and adaptive time-partitioning ensure critical tasks run and complete when required. It repeats the IEC 61508 SIL 3 and ISO 26262 ASIL D claims. — [QNX Robotics Solution Guide (PDF)](https://qnx.software/content/dam/qnx-xwalk/pdf/solution-guides/qnx-robotics-solution-guide.pdf). The PDF text could not be extracted directly.
- QNX SDP 8.0 messaging also mentions time-triggered scheduling and data-flow-driven execution. — [QNX SDP 8.0](https://qnx.software/en/software/products-and-solutions/qnx-software-development-platform)

### Inferences
Suggested pitch lines. Each uses QNX's own terms and is honest about what the team built:
- "Each function runs in its own process: vision, classifier, gripper control, supervisor. In a microkernel, drivers and services run in user space, so a vision crash cannot take down force control. That's spatial isolation."
- "The gripper loop runs at real-time priority under QNX's priority-based preemptive scheduler. Under CPU load, worst-case lateness was 0.49 ms versus 137 ms at normal priority. That's temporal determinism, and we measured it."
- "Our supervisor restarts crashed processes while the arm keeps holding the object. A fault is contained and recovered, not fatal."
- "The e-stop fails safe: loss of signal means stop."
- "QNX OS for Safety is certified to IEC 62304 Class C, the medical-device software standard, so this architecture has a credible path to a certified assistive device."
- Do not claim the hackathon build is certified or uses QNX OS for Safety. QNX Everywhere on a Pi is the standard SDP 8.0, not the safety-certified variant. Say "the same RTOS family that's certified for…".
- "Priority-based preemptive scheduling" and "process isolation" are standard descriptions of QNX Neutrino, but neither was quoted verbatim in the pages I opened. The verbatim terms are "spatial and temporal isolation", "deterministic", "microkernel" and "priority-based scheduling".

### Gaps
- I could not read the robotics solution guide PDF, so its exact quotes are unverified. I found no QNX-published latency figures to compare against the team's 0.49 ms.

## (d) Health problem: who has grip weakness or hand impairment, and what do existing assistive arms cost?

### Takeaway
In Canada, more than 1.5 million people aged 15 and over (5.0%) have a dexterity disability, meaning difficulty grasping small objects with their fingers. That rises to 11.3% at age 65 and over, and 28% report unmet support needs because of cost (StatCan, Canadian Survey on Disability 2022). About 6 million Canadians live with arthritis, and more than 400,000 live with long-term disability from stroke. Commercial options are expensive: a Kinova JACO assistive arm costs about USD 35,000 to 50,000, and the Obi feeding robot about USD 8,000 to 13,000 at current retail. A low-cost, fail-safe pick-and-place helper speaks directly to that cost gap.

### Cited Findings
- **Dexterity disability, StatCan CSD 2022:**
  - 5.0% of Canadians aged 15 and over, more than 1.5 million people.
  - 1.2% at ages 15 to 24, rising to 11.3% at 65 and over.
  - 5.7% of women and gender-diverse people versus 4.2% of men.
  - Defined as difficulty or inability using fingers to grasp small objects, which limits daily activities.
  - 86% also have a pain-related disability.
  - 28% have unmet needs for disability supports because of cost.

  These figures come from a search summary of the StatCan infographic and release. A direct fetch returned 403, so verify the numbers on the page. — [StatCan: Dexterity disabilities, 2022](https://www150.statcan.gc.ca/n1/pub/11-627-m/11-627-m2024054-eng.htm); [StatCan infographic](https://www.statcan.gc.ca/o1/en/app/7469-infographic-dexterity-disabilities-2022)
- **Arthritis:**
  - StatCan 2023 figures: arthritis prevalence is about 19.5% of adults aged 18 and over in population centres and 26.2% in rural areas. — [StatCan Daily, 2025-03-05 chart](https://www150.statcan.gc.ca/n1/daily-quotidien/250305/cg-a002-eng.htm)
  - Arthritis Society Canada says about 6 million Canadians live with arthritis (Oct 2023 report card, based on CCHS 2015 to 2021) and projects 9 million by 2045. — [Arthritis Society Canada Report Card (PDF)](https://arthrite.ca/getmedia/0c7b1abc-8f14-4fea-bc8d-3225b6d30e53/Arthritis-Canada-Report-Card_Final_Oct5.pdf); [Arthritis Society news](https://arthritis.ca/about-us/news-stories/new-report-highlights-significant-gaps-arthritis-care-research-across-canada/)
  - Statista, citing CCHS, reports about 6.3 million Canadians diagnosed with arthritis in 2022. This is an aggregator. — [Statista](https://statista.com/statistics/434082/number-of-canadians-reporting-being-diagnosed-with-arthritis)
- **Hand osteoarthritis:**
  - Osteoarthritis Initiative cohort, 2022 analysis of 3,588 participants: radiographic hand OA 41.4%, symptomatic hand OA 12.4%. This is a US cohort. — [PMC9791555](https://pmc.ncbi.nlm.nih.gov/articles/PMC9791555)
  - A 2022 Turkish multicentre cohort linked symptomatic hand OA to weak grip strength and impaired hand function, mediated by pain. This came from a search summary. — [PMC12302428](https://pmc.ncbi.nlm.nih.gov/articles/PMC12302428/)
- **Stroke:** more than 400,000 Canadians live with long-term disability from stroke, a number expected to almost double in 20 years. — [Heart & Stroke news release](https://www.heartandstroke.ca/what-we-do/media-centre/news-releases/help-wanted-needs-not-being-met-for-canadians-living-with-stroke). Canadian Stroke Best Practice Recommendations (2019) note that reduced arm and hand function is common and impairs dressing and bathing. — [CSBPR Rehabilitation module](https://www.heartandstroke.ca/-/media/1-stroke-best-practices/rehabilitation-nov2019/2019-csbpr6-rehabrecovery-module-eng-final-dec2019.ashx)
- **Kinova JACO** (Canadian, Montreal-based assistive arm, wheelchair-mountable):
  - Commonly cited at about USD 35,000, and reported as not covered by US insurers. — [Futurism](https://futurism.com/the-byte/robot-arm-wheelchair)
  - Database listings give USD 35,000 to 50,000. A UK retailer lists it as "price on application". — [livingmadeeasy.org.uk](https://livingmadeeasy.org.uk/product/jaco-assistve-robotic-arm); [Kinova brochure](https://www.kinovarobotics.com/uploads/Jaco-Robotic-Arm-Brochure-EN.pdf)
  - These prices are not recent.
- **Obi feeding robot:**
  - USD 4,500 at launch in 2016. — [The Robot Report](https://www.therobotreport.com/obi-dining-robot-helps-disabled-people-feed-themselves/)
  - Current Obi 3 retail is about USD 8,200 to 12,950. — [Rehab-Store](https://www.rehab-store.com/p-obi-robotic-independent-feeding-device.html); [HealthProductsForYou](https://www.healthproductsforyou.com/p-obi-robotic-independent-feeding-device.html)
  - About £6,105 in the UK and €9,900 in Ireland. — [livingmadeeasy.org.uk](https://livingmadeeasy.org.uk/product/obi-robotic-eating-device); [HomeCare Medical Supplies IE](https://www.homecaremedicalsupplies.ie/products/obi-robotic-feeding-device)

### Inferences
- A "who it helps" line: "1.5 million Canadians have trouble grasping objects, and more than 1 in 10 seniors do. A JACO arm costs about $35–50K USD, and 28% of Canadians with dexterity disabilities already go without supports because of cost. We built a pointing-controlled pick-and-place helper on a Raspberry Pi."
- The force-controlled gripper and the "arm keeps holding during a process crash" demo answer the safety concern that matters most for users who can't catch a dropped object (hot mug, medication). Frame reliability as patient safety, not just engineering.
- Pointing control suits users with grip weakness but intact arm movement, such as arthritis, mild post-stroke impairment or tremor. Avoid claiming clinical efficacy. Say "designed for" rather than "proven for".
- Keep the parts cost claim to whatever the team actually spent. Don't compare a prototype to certified medical devices as if they were equivalent.

### Gaps
- I found no reliable recent Canadian prevalence figure for essential tremor, or for post-stroke upper-limb impairment as a share. Avoid citing specific numbers for these.
- I found no current official list price for Kinova JACO. Price data comes from secondary sources and is dated.
- I did not check Canadian funding programs (for example Ontario's Assistive Devices Program) for whether they cover robotic arms.
