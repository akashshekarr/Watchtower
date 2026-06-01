"""
usage_tracker.py
----------------
Wrap your LLM calls so every request is logged to SQLite with
provider, key label, model, tokens, and computed cost.

Usage:
    from usage_tracker import UsageTracker
    tracker = UsageTracker()

    # After any API call where you have a usage object:
    tracker.log("openai", key_label="prod-key-1", model="gpt-4o",
                input_tokens=1200, output_tokens=350)

    # Or use the convenience wrappers (see bottom of file).
"""

import sqlite3
import datetime as dt
import hashlib
from contextlib import closing
from pricing import cost_for

DB_PATH = "usage.db"


class UsageTracker:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with closing(sqlite3.connect(self.db_path)) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS usage (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts            TEXT NOT NULL,
                    provider      TEXT NOT NULL,
                    key_label     TEXT NOT NULL,
                    key_hash      TEXT,
                    model         TEXT NOT NULL,
                    input_tokens  INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    total_tokens  INTEGER NOT NULL,
                    cost_usd      REAL NOT NULL
                )
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_provider ON usage(provider)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_ts ON usage(ts)")
            con.commit()

    @staticmethod
    def _hash_key(api_key: str | None) -> str | None:
        if not api_key:
            return None
        return hashlib.sha256(api_key.encode()).hexdigest()[:12]

    def log(self, provider: str, key_label: str, model: str,
            input_tokens: int, output_tokens: int,
            api_key: str | None = None, ts: str | None = None) -> float:
        cost = cost_for(provider, model, input_tokens, output_tokens)
        ts = ts or dt.datetime.now(dt.timezone.utc).isoformat()
        with closing(sqlite3.connect(self.db_path)) as con:
            con.execute(
                """INSERT INTO usage
                   (ts, provider, key_label, key_hash, model,
                    input_tokens, output_tokens, total_tokens, cost_usd)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (ts, provider, key_label, self._hash_key(api_key), model,
                 input_tokens, output_tokens,
                 input_tokens + output_tokens, cost),
            )
            con.commit()
        return cost


# ---------------------------------------------------------------------------
# Convenience wrappers — call these INSTEAD of the raw SDK call, and they
# both make the request and log it. Adapt arg names to your SDK versions.
# ---------------------------------------------------------------------------

_tracker = UsageTracker()


def openai_chat(client, key_label, model, **kwargs):
    resp = client.chat.completions.create(model=model, **kwargs)
    u = resp.usage
    _tracker.log("openai", key_label, model,
                 u.prompt_tokens, u.completion_tokens)
    return resp


def anthropic_message(client, key_label, model, **kwargs):
    resp = client.messages.create(model=model, **kwargs)
    u = resp.usage
    _tracker.log("anthropic", key_label, model,
                 u.input_tokens, u.output_tokens)
    return resp


def gemini_generate(model_obj, key_label, model_name, *args, **kwargs):
    resp = model_obj.generate_content(*args, **kwargs)
    um = resp.usage_metadata
    _tracker.log("gemini", key_label, model_name,
                 um.prompt_token_count, um.candidates_token_count)
    return resp


def groq_chat(client, key_label, model, **kwargs):
    resp = client.chat.completions.create(model=model, **kwargs)
    u = resp.usage
    _tracker.log("groq", key_label, model,
                 u.prompt_tokens, u.completion_tokens)
    return resp