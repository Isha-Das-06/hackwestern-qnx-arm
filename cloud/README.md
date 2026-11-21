# PickVision cloud history (Tiger Data + Vultr)

The robot runs **fully offline on QNX**. This only keeps its history:

```
QNX Pi (python/cloud_sync.py)  --HTTPS batches-->  Vultr server (server.py)  -->  Tiger Data (TimescaleDB)
   queues + saves to disk when offline                  also serves the dashboard
```

- **Moves:** object, from/to box, finished or why not, reaction time, robot time.
- **Health:** every 10 s: fps, average/worst frame time, % frames under the 200 ms budget, CPU.
- **Tiger Data features used:** hypertables (`moves`, `health`), a continuous aggregate
  `health_1m` (per-minute health, refreshed every minute), compression of raw health after 7 days.
  The dashboard reads the per-minute aggregate for long ranges.
- Resent records (e.g. after a timeout) are skipped by id, so nothing is counted twice.

## Set up

1. **Tiger Data:** make a service on Tiger Cloud, copy its connection string (`postgres://...`).
2. **Vultr:** make an Ubuntu 24.04 server (the smallest plan is enough). Then from the laptop:
   ```
   scp -r cloud root@<vultr-ip>:/root/
   ssh root@<vultr-ip> sh /root/cloud/setup_vultr.sh
   ```
   It asks for the connection string, makes a token, starts the service, and prints the
   dashboard link plus the line to put on the Pi.
3. **Pi:** save that line as `~/pickvision/config/cloud.json`, then restart the app.
   No file = cloud off. The token file is not committed.

## Test locally

```
python -m venv cloud\.venv
cloud\.venv\Scripts\pip install -r cloud\requirements.txt
set DATABASE_URL=postgres://...   &  set INGEST_TOKEN=anything
cloud\.venv\Scripts\python -m uvicorn server:app --app-dir cloud --port 8099
```

Works on plain Postgres too (the Tiger features are skipped and shown crossed out on the page).
