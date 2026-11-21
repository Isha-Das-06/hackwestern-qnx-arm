# Handoff: start a new chat from here

Paste this into a new Claude chat (or say "read HANDOFF.md and GAMEPLAN.md first").
No passwords in this file.

## Who / what
- Isha, Hack Western 13 (QNX track). Beginner: **one short step at a time**, do the work for her.
- **Never push to GitHub without asking first, every time.** She tests first.
- Project: PickVision, the vision part of a pick-and-place robot. Python on a QNX Raspberry Pi 4.
- Deadlines: Devpost **Sun 9:00 AM**, demo fair **Sun 12–1 PM**. No slide decks.

## Where things are
- Code: `Desktop\projects claude\qnx hw` (not a git repo).
- GitHub copy: `Desktop\projects claude\qnx-arm-repo`, branch `isha-code` on
  https://github.com/Isha-Das-06/hackwestern-qnx-arm (to push: copy changes over, commit, push in the background, since pushes take >2 min).
- Pi: `qnxuser@192.168.8.247`, key `~/.ssh/pickvision_pi`, needs `-c aes128-ctr -o MACs=hmac-sha2-256`.
  App: `~/pickvision/run_pi.sh` (start) / `run_pi.sh stop`. Console: http://192.168.8.247:8080
- Vultr: `root@66.42.92.71`, key `~/.ssh/pickvision_vultr`. Dashboard: http://66.42.92.71
- Tiger Data: free service `pickvision`; credentials in `Downloads\tiger-cloud-pickvision-credentials.txt`
  (read only by scripts, never print it).
- Full details: `GAMEPLAN.md` (status, cloud setup, gaps) and `CHAT_SUMMARY.md` (decisions, history).

## Done in the Nov 21 afternoon chat
1. Console fixes on the Pi: Teach buttons reliable, teach from the most-changed box, clear per object,
   Set up kept open on refresh, louder sounds, "Unknown" label, stricter unknown limit (4.2).
2. Camera moved higher; egg (charger stand-in), cup, block taught, 5 each.
3. Pushed the vision code to `isha-code` (QNX headers left out: licence).
4. Built + tested the cloud history: Pi sender → Vultr server → Tiger Data (hypertables,
   continuous aggregate, compression) → dashboard. Live at http://66.42.92.71. Pi test send worked.
5. Checked the teammates' Pi code (`~/mks_servo`): only motor driver + test, no control task yet.

## Right now
- The Pi app is **stopped**: the camera wasn't found. **Next step: replug the USB webcam, then start the app**
  and do a real move. It should appear on the dashboard within seconds.
- Not pushed yet: `cloud/setup_vultr.sh` (strip Windows `\r`), `GAMEPLAN.md`, this file. Ask first.

## Still open
- **Arm wiring (most important for the QNX prize):** ask the teammates how they want the pick message.
- Real grip numbers in `config/grip.yml`; a real egg (re-teach: Clear examples → Egg).
- Before each judge: new empty-tray photo (lighting drift).
- Backup demo video. Devpost write-up.
- After the hackathon: **Destroy** the Vultr server (Stop still charges).
