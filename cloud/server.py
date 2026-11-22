"""
PickVision cloud history: receives move + health records from the QNX Pi and
stores them in Tiger Data (TimescaleDB); serves the history dashboard.

The robot does not depend on this - it runs fully offline on QNX and only sends
history here when it can.

Env:
  DATABASE_URL   Tiger Cloud connection string (postgres://...?sslmode=require)
  INGEST_TOKEN   shared secret; the Pi sends it as "Authorization: Bearer ..."

Run:  uvicorn server:app --host 0.0.0.0 --port 80
"""

import datetime as dt
import hmac
import os
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

HERE = pathlib.Path(__file__).parent
DB_URL = os.environ.get("DATABASE_URL", "")
TOKEN = os.environ.get("INGEST_TOKEN", "")

pool = None
features = {"timescale": False, "aggregate": False, "compression": False}

SCHEMA = """
CREATE TABLE IF NOT EXISTS moves (
    time        timestamptz NOT NULL,
    id          text        NOT NULL,
    device      text        NOT NULL,
    obj         text,
    from_box    int,
    to_box      int,
    status      text        NOT NULL,   -- done | rejected | cancelled | no-response
    note        text,
    grip_lo     int,
    grip_hi     int,
    react_ms    int,                    -- hand leaves "to" box -> command sent
    identify_ms int,
    choose_s    real,
    robot_s     real
);
CREATE UNIQUE INDEX IF NOT EXISTS moves_id ON moves (id, time);   -- also makes the resend check fast
CREATE TABLE IF NOT EXISTS health (
    time        timestamptz NOT NULL,
    id          text        NOT NULL,
    device      text        NOT NULL,
    fps         real,
    frame_ms    real,
    worst_ms    real,
    ontime_pct  real,                   -- % of frames under the 200 ms budget
    cpu_pct     real,
    hand_ms     real
);
CREATE UNIQUE INDEX IF NOT EXISTS health_id ON health (id, time);
"""

# Tiger Data / TimescaleDB features. Each step is optional so the server still
# runs on plain Postgres (e.g. a local test without the extension).
TIMESCALE_STEPS = [
    ("timescale", "CREATE EXTENSION IF NOT EXISTS timescaledb"),
    ("timescale", "SELECT create_hypertable('moves', 'time', if_not_exists => TRUE, migrate_data => TRUE)"),
    ("timescale", "SELECT create_hypertable('health', 'time', if_not_exists => TRUE, migrate_data => TRUE)"),
    # per-minute health summary that keeps itself up to date
    ("aggregate", """
        CREATE MATERIALIZED VIEW IF NOT EXISTS health_1m
        WITH (timescaledb.continuous) AS
        SELECT time_bucket('1 minute', time) AS bucket, device,
               avg(fps) AS fps, avg(frame_ms) AS frame_ms, max(worst_ms) AS worst_ms,
               avg(ontime_pct) AS ontime_pct, avg(cpu_pct) AS cpu_pct, count(*) AS samples
        FROM health GROUP BY bucket, device WITH NO DATA"""),
    # real-time: also include rows newer than the last refresh, so the dashboard is current
    ("aggregate", "ALTER MATERIALIZED VIEW health_1m SET (timescaledb.materialized_only = false)"),
    ("aggregate", """
        SELECT add_continuous_aggregate_policy('health_1m',
            start_offset => INTERVAL '2 days', end_offset => INTERVAL '1 minute',
            schedule_interval => INTERVAL '1 minute', if_not_exists => TRUE)"""),
    # old raw health samples get compressed (the per-minute summary stays)
    ("compression", "ALTER TABLE health SET (timescaledb.compress, timescaledb.compress_segmentby = 'device')"),
    ("compression", "SELECT add_compression_policy('health', INTERVAL '7 days', if_not_exists => TRUE)"),
]


def setup_db():
    with pool.connection() as conn:
        conn.execute(SCHEMA)
        conn.commit()
        ok = {}
        for name, sql in TIMESCALE_STEPS:
            if ok.get(name) is False or (name != "timescale" and not ok.get("timescale")):
                continue
            try:
                # CREATE MATERIALIZED VIEW ... continuous can't run inside a transaction
                conn.autocommit = True
                conn.execute(sql)
                ok[name] = True
            except Exception as e:
                print(f"[db] {name} step skipped: {str(e).splitlines()[0]}")
                ok[name] = False
            finally:
                conn.autocommit = False
        features.update({k: bool(v) for k, v in ok.items()})
    print(f"[db] ready - features: {features}")


@asynccontextmanager
async def lifespan(_app):
    global pool
    if not DB_URL or not TOKEN:
        raise SystemExit("set DATABASE_URL and INGEST_TOKEN")
    pool = ConnectionPool(DB_URL, min_size=1, max_size=5, open=True,
                          kwargs={"row_factory": dict_row})
    setup_db()
    yield
    pool.close()


app = FastAPI(title="PickVision history", lifespan=lifespan)


# ------------------------------------------------------------------ ingest (from the Pi)
class Batch(BaseModel):
    device: str
    records: list[dict]


def _num(v, cast=float):
    try:
        return None if v is None else cast(v)
    except (TypeError, ValueError):
        return None


@app.post("/api/ingest")
def ingest(batch: Batch, authorization: str = Header(default="")):
    if not hmac.compare_digest(authorization.encode(), f"Bearer {TOKEN}".encode()):
        raise HTTPException(401, "bad token")
    now = dt.datetime.now(dt.timezone.utc)
    dev = batch.device[:64]
    moves, health = [], []
    for r in batch.records[:1000]:
        age = _num(r.get("age_s")) or 0.0
        t = now - dt.timedelta(seconds=min(max(age, 0.0), 365 * 86400))
        rid = str(r.get("id", ""))[:64]
        if not rid:
            continue
        if r.get("kind") == "move":
            g = r.get("grip") if isinstance(r.get("grip"), list) and len(r["grip"]) == 2 else [None, None]
            moves.append((t, rid, dev, str(r.get("obj") or "")[:16], _num(r.get("from_box"), int),
                          _num(r.get("to_box"), int), str(r.get("status") or "")[:16],
                          str(r.get("note") or "")[:200], _num(g[0], int), _num(g[1], int),
                          _num(r.get("react_ms"), int), _num(r.get("identify_ms"), int),
                          _num(r.get("choose_s")), _num(r.get("robot_s"))))
        elif r.get("kind") == "health":
            health.append((t, rid, dev, _num(r.get("fps")), _num(r.get("frame_ms")),
                           _num(r.get("worst_ms")), _num(r.get("ontime_pct")),
                           _num(r.get("cpu_pct")), _num(r.get("hand_ms"))))
    # A resend (the Pi didn't hear our reply) arrives with a slightly different computed
    # time, so skip any id already stored within a day of it.
    skip = "WHERE NOT EXISTS (SELECT 1 FROM {t} WHERE id = %s AND time BETWEEN %s - INTERVAL '1 day' AND %s + INTERVAL '1 day')"
    with pool.connection() as conn, conn.cursor() as cur:
        if moves:
            cur.executemany("""INSERT INTO moves (time, id, device, obj, from_box, to_box, status, note,
                               grip_lo, grip_hi, react_ms, identify_ms, choose_s, robot_s)
                               SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s """ + skip.format(t="moves")
                            + " ON CONFLICT DO NOTHING", [m + (m[1], m[0], m[0]) for m in moves])
        if health:
            cur.executemany("""INSERT INTO health (time, id, device, fps, frame_ms, worst_ms,
                               ontime_pct, cpu_pct, hand_ms)
                               SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s """ + skip.format(t="health")
                            + " ON CONFLICT DO NOTHING", [h + (h[1], h[0], h[0]) for h in health])
    return {"ok": True, "moves": len(moves), "health": len(health)}


# ------------------------------------------------------------------ dashboard data
def _bucket(hours):
    return "1 minute" if hours <= 1 else "5 minutes" if hours <= 6 else "30 minutes" if hours <= 48 else "6 hours"


@app.get("/api/summary")
def summary(hours: float = Query(24, gt=0, le=24 * 30)):
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    b = _bucket(hours)
    tb = "time_bucket(%s::interval, time)" if features["timescale"] else "date_bin(%s::interval, time, 'epoch')"
    with pool.connection() as conn:
        q = lambda sql, *a: conn.execute(sql, a).fetchall()  # noqa: E731
        k = q("""SELECT count(*) AS moves,
                        count(*) FILTER (WHERE status = 'done') AS done,
                        percentile_cont(0.5) WITHIN GROUP (ORDER BY react_ms) AS react_p50,
                        percentile_cont(0.95) WITHIN GROUP (ORDER BY react_ms) AS react_p95,
                        max(time) AS last_move
                 FROM moves WHERE time >= %s""", since)[0]
        hk = q("""SELECT avg(ontime_pct) AS ontime_pct, avg(fps) AS fps, max(time) AS last_seen,
                         count(*) AS samples
                  FROM health WHERE time >= %s""", since)[0]
        last_seen = q("SELECT max(time) AS t FROM health")[0]["t"]
        over_time = q(f"""SELECT {tb} AS t,
                                 count(*) FILTER (WHERE status = 'done') AS done,
                                 count(*) FILTER (WHERE status <> 'done') AS not_done
                          FROM moves WHERE time >= %s GROUP BY 1 ORDER BY 1""", b, since)
        by_obj = q("""SELECT obj, count(*) AS moves, count(*) FILTER (WHERE status = 'done') AS done
                      FROM moves WHERE time >= %s AND obj <> '' GROUP BY obj ORDER BY obj""", since)
        reasons = q("""SELECT status, note, count(*) AS n FROM moves
                       WHERE time >= %s AND status <> 'done' GROUP BY status, note ORDER BY n DESC LIMIT 6""",
                    since)
        if features["aggregate"] and hours > 1:
            # read the continuous aggregate (pre-computed per minute), re-bucketed for the range
            perf = q("""SELECT time_bucket(%s::interval, bucket) AS t, avg(frame_ms) AS frame_ms,
                               max(worst_ms) AS worst_ms, avg(ontime_pct) AS ontime_pct, avg(fps) AS fps
                        FROM health_1m WHERE bucket >= %s GROUP BY 1 ORDER BY 1""", b, since)
        else:
            perf = q(f"""SELECT {tb} AS t, avg(frame_ms) AS frame_ms, max(worst_ms) AS worst_ms,
                                avg(ontime_pct) AS ontime_pct, avg(fps) AS fps
                         FROM health WHERE time >= %s GROUP BY 1 ORDER BY 1""", b, since)
        recent = q("""SELECT time, obj, from_box, to_box, status, note, react_ms, robot_s
                      FROM moves ORDER BY time DESC LIMIT 15""")
    return {"hours": hours, "bucket": b, "features": features,
            "now": dt.datetime.now(dt.timezone.utc), "last_seen": last_seen,
            "kpi": {**k, **hk}, "over_time": over_time, "by_obj": by_obj, "reasons": reasons,
            "perf": perf, "recent": recent}


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def dashboard():
    return FileResponse(HERE / "dashboard.html")
