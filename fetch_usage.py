"""
fetch_usage.py
--------------
Pulls per-API-key usage + cost from OpenAI and Anthropic Admin APIs and
stores it in SQLite. No changes to your application code required.

Run:
    python fetch_usage.py              # last 30 days
    python fetch_usage.py --days 7     # last 7 days

Set these environment variables first (do NOT hard-code keys):
    OPENAI_ADMIN_KEY      = sk-admin-...
    ANTHROPIC_ADMIN_KEY   = sk-ant-admin-...

What you get per provider:
  OpenAI    : cost per api_key_id (from /organization/costs)
              + tokens per api_key_id (from /organization/usage/completions)
  Anthropic : tokens per api_key_id (from /usage_report/messages)
              cost computed from those tokens via pricing.py
"""

import os
import time
import argparse
import sqlite3
import datetime as dt
from contextlib import closing

import requests

from pricing import cost_for

DB_PATH = "usage.db"


def _load_dotenv(path=".env"):
    """Load KEY=VALUE lines from a .env file into os.environ (no library needed).
    Existing real environment variables take precedence and are not overwritten."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")  # drop optional quotes
            os.environ.setdefault(key, val)


_load_dotenv()

OPENAI_ADMIN_KEY = os.environ.get("OPENAI_ADMIN_KEY")
ANTHROPIC_ADMIN_KEY = os.environ.get("ANTHROPIC_ADMIN_KEY")


# ---------------------------------------------------------------------------
# Storage. We store a daily snapshot per (provider, key, model, date) so
# re-running is idempotent — the UNIQUE constraint + REPLACE avoids dupes.
# ---------------------------------------------------------------------------
def init_db():
    with closing(sqlite3.connect(DB_PATH)) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS daily_usage (
                day           TEXT NOT NULL,
                provider      TEXT NOT NULL,
                key_id        TEXT NOT NULL,
                key_label     TEXT,
                model         TEXT NOT NULL,
                input_tokens  INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd      REAL NOT NULL DEFAULT 0,
                UNIQUE(day, provider, key_id, model)
            )
        """)
        con.commit()

        # --- Self-heal: an older DB may have this table WITHOUT the UNIQUE
        # constraint, which breaks the upsert. Detect and migrate if so. ---
        has_unique = False
        for row in con.execute("PRAGMA index_list('daily_usage')"):
            # row: (seq, name, unique, origin, partial)
            if row[2] == 1:  # a unique index exists
                has_unique = True
                break
        if not has_unique:
            print("  [db] migrating old table to add UNIQUE constraint...")
            con.execute("ALTER TABLE daily_usage RENAME TO daily_usage_old")
            con.execute("""
                CREATE TABLE daily_usage (
                    day           TEXT NOT NULL,
                    provider      TEXT NOT NULL,
                    key_id        TEXT NOT NULL,
                    key_label     TEXT,
                    model         TEXT NOT NULL,
                    input_tokens  INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    cost_usd      REAL NOT NULL DEFAULT 0,
                    UNIQUE(day, provider, key_id, model)
                )
            """)
            # Carry over any old rows, collapsing duplicates.
            con.execute("""
                INSERT OR REPLACE INTO daily_usage
                  (day, provider, key_id, key_label, model,
                   input_tokens, output_tokens, cost_usd)
                SELECT day, provider, key_id, key_label, model,
                       input_tokens, output_tokens, cost_usd
                FROM daily_usage_old
            """)
            con.execute("DROP TABLE daily_usage_old")
            con.commit()


def upsert(rows):
    with closing(sqlite3.connect(DB_PATH)) as con:
        con.executemany("""
            INSERT INTO daily_usage
              (day, provider, key_id, key_label, model,
               input_tokens, output_tokens, cost_usd)
            VALUES (:day,:provider,:key_id,:key_label,:model,
                    :input_tokens,:output_tokens,:cost_usd)
            ON CONFLICT(day, provider, key_id, model) DO UPDATE SET
              input_tokens=excluded.input_tokens,
              output_tokens=excluded.output_tokens,
              cost_usd=excluded.cost_usd,
              key_label=excluded.key_label
        """, rows)
        con.commit()


def day_str(unix_ts):
    return dt.datetime.fromtimestamp(unix_ts, dt.timezone.utc).strftime("%Y-%m-%d")


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def get_or_explain(url, headers, params, provider):
    """GET that prints the API's real error message instead of a bare 401."""
    r = requests.get(url, headers=headers, params=params, timeout=60)
    if not r.ok:
        body = ""
        try:
            body = r.json().get("error", {}).get("message", "") or r.text
        except Exception:
            body = r.text
        print(f"\n  [{provider}] HTTP {r.status_code} from {url.split('?')[0]}")
        print(f"  [{provider}] API says: {body}\n")
        r.raise_for_status()
    return r


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
def fetch_openai(start_ts):
    if not OPENAI_ADMIN_KEY:
        print("  [openai] OPENAI_ADMIN_KEY not set — skipping")
        return []

    headers = {"Authorization": f"Bearer {OPENAI_ADMIN_KEY}",
               "Content-Type": "application/json"}
    rows = {}  # (day, key_id, model) -> row dict

    # --- Tokens per key + model (usage/completions) ---
    url = "https://api.openai.com/v1/organization/usage/completions"
    params = {"start_time": start_ts, "bucket_width": "1d",
              "group_by": ["api_key_id", "model"], "limit": 31}
    cursor = None
    while True:
        if cursor:
            params["page"] = cursor
        r = get_or_explain(url, headers, params, "openai")
        data = r.json()
        for bucket in data.get("data", []):
            day = day_str(bucket["start_time"])
            for res in bucket.get("results", []):
                key_id = res.get("api_key_id") or "unknown"
                model = res.get("model") or "unknown"
                k = (day, key_id, model)
                rows.setdefault(k, {
                    "day": day, "provider": "openai", "key_id": key_id,
                    "key_label": key_id, "model": model,
                    "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
                rows[k]["input_tokens"] += _int(res.get("input_tokens", 0))
                rows[k]["output_tokens"] += _int(res.get("output_tokens", 0))
        if data.get("has_more") and data.get("next_page"):
            cursor = data["next_page"]
        else:
            break

    # --- Authoritative cost per key (organization/costs) ---
    # Cost here is not split by model, so we attach it to the key's row set
    # by distributing onto a synthetic '_cost' model line to stay accurate.
    url = "https://api.openai.com/v1/organization/costs"
    params = {"start_time": start_ts, "bucket_width": "1d",
              "group_by": ["api_key_id"], "limit": 180}
    cursor = None
    cost_by_day_key = {}
    while True:
        if cursor:
            params["page"] = cursor
        r = get_or_explain(url, headers, params, "openai")
        data = r.json()
        for bucket in data.get("data", []):
            day = day_str(bucket["start_time"])
            for res in bucket.get("results", []):
                key_id = res.get("api_key_id") or "unknown"
                amt = (res.get("amount") or {}).get("value", 0.0)
                try:
                    amt = float(amt)
                except (TypeError, ValueError):
                    amt = 0.0
                cost_by_day_key[(day, key_id)] = \
                    cost_by_day_key.get((day, key_id), 0.0) + amt
        if data.get("has_more") and data.get("next_page"):
            cursor = data["next_page"]
        else:
            break

    # Attach authoritative cost: put it on the largest-token model row for
    # that day+key (so totals reconcile to the bill). If no token rows exist
    # for that day+key, create a cost-only row.
    for (day, key_id), amt in cost_by_day_key.items():
        candidates = [k for k in rows if k[0] == day and k[1] == key_id]
        if candidates:
            best = max(candidates,
                       key=lambda k: rows[k]["input_tokens"] + rows[k]["output_tokens"])
            rows[best]["cost_usd"] += amt
        else:
            k = (day, key_id, "_cost_only")
            rows[k] = {"day": day, "provider": "openai", "key_id": key_id,
                       "key_label": key_id, "model": "_cost_only",
                       "input_tokens": 0, "output_tokens": 0, "cost_usd": amt}

    print(f"  [openai] {len(rows)} day/key/model rows")
    return list(rows.values())


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------
def fetch_anthropic(start_iso):
    if not ANTHROPIC_ADMIN_KEY:
        print("  [anthropic] ANTHROPIC_ADMIN_KEY not set — skipping")
        return []

    headers = {"x-api-key": ANTHROPIC_ADMIN_KEY,
               "anthropic-version": "2023-06-01",
               "content-type": "application/json"}
    url = "https://api.anthropic.com/v1/organizations/usage_report/messages"
    params = {"starting_at": start_iso, "bucket_width": "1d",
              "group_by[]": ["api_key_id", "model"], "limit": 31}

    rows = {}
    cursor = None
    while True:
        if cursor:
            params["page"] = cursor
        r = get_or_explain(url, headers, params, "anthropic")
        data = r.json()
        for bucket in data.get("data", []):
            day = bucket["starting_at"][:10]
            for res in bucket.get("results", []):
                key_id = res.get("api_key_id") or "unknown"
                model = res.get("model") or "unknown"
                in_tok = (_int(res.get("uncached_input_tokens", 0))
                          + _int(res.get("cache_read_input_tokens", 0)))
                cc = res.get("cache_creation") or {}
                in_tok += _int(cc.get("ephemeral_1h_input_tokens", 0))
                in_tok += _int(cc.get("ephemeral_5m_input_tokens", 0))
                out_tok = _int(res.get("output_tokens", 0))
                cost = cost_for("anthropic", model, in_tok, out_tok)
                k = (day, key_id, model)
                rows.setdefault(k, {
                    "day": day, "provider": "anthropic", "key_id": key_id,
                    "key_label": key_id, "model": model,
                    "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
                rows[k]["input_tokens"] += in_tok
                rows[k]["output_tokens"] += out_tok
                rows[k]["cost_usd"] += cost
        if data.get("has_more") and data.get("next_page"):
            cursor = data["next_page"]
        else:
            break

    print(f"  [anthropic] {len(rows)} day/key/model rows")
    return list(rows.values())


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30,
                    help="How many days back to pull (default 30)")
    args = ap.parse_args()

    init_db()
    now = int(time.time())
    start_ts = now - args.days * 86400
    start_iso = dt.datetime.fromtimestamp(
        start_ts, dt.timezone.utc).strftime("%Y-%m-%dT00:00:00Z")

    print(f"Fetching last {args.days} days...")
    rows = []
    rows += fetch_openai(start_ts)
    rows += fetch_anthropic(start_iso)

    if rows:
        upsert(rows)
        total = sum(r["cost_usd"] for r in rows)
        print(f"Stored {len(rows)} rows. Total cost in range: ${total:,.2f}")
    else:
        print("No rows fetched. Check that your admin keys are set.")


if __name__ == "__main__":
    main()