# LLM API Usage Dashboard (pull-based)

Pulls **per-API-key** cost + tokens from OpenAI and Anthropic admin APIs.
No changes to your application code. One script fetches; a Streamlit
dashboard displays.

## Why this approach
Both OpenAI and Anthropic already track per-key usage server-side. With an
**admin key** for each org you just pull those numbers — far simpler than
wrapping every call across many apps and keys.

## Files
- `fetch_usage.py`  — pulls data from both providers into `usage.db`.
- `dashboard.py`    — Streamlit UI (run after fetching).
- `pricing.py`      — token prices; used to compute Anthropic per-key cost.
- `key_names.py`    — OPTIONAL map of key IDs -> friendly names.
- `usage_tracker.py`, `test_log.py` — only needed if you also self-log Groq/Gemini.

## Setup
```bash
pip install streamlit pandas requests
```

Get admin keys (one-time):
- OpenAI:    https://platform.openai.com/settings/organization/admin-keys
- Anthropic: Console -> Settings -> Admin keys  (key starts with sk-ant-admin-)

Set them as environment variables (never hard-code):

**Windows (PowerShell):**
```powershell
$env:OPENAI_ADMIN_KEY="sk-admin-..."
$env:ANTHROPIC_ADMIN_KEY="sk-ant-admin-..."
```

**Mac/Linux:**
```bash
export OPENAI_ADMIN_KEY="sk-admin-..."
export ANTHROPIC_ADMIN_KEY="sk-ant-admin-..."
```

## Use
```bash
python fetch_usage.py --days 30     # pull last 30 days
streamlit run dashboard.py          # view it
```
Re-run `fetch_usage.py` any time to refresh — it's idempotent (no duplicates).
To automate, schedule it (Windows Task Scheduler / cron) to run daily.

## Friendly key names (optional)
The APIs return key IDs (e.g. `key_VVawtqw...`), not names. Open `key_names.py`
and map the IDs to the names from your provider dashboards. The OpenAI
"Tracking ID" column IS the key_id. Unmapped IDs simply show as-is.

## Notes
- OpenAI cost is authoritative (from the Costs endpoint, reconciles to your bill).
  Anthropic per-key cost is computed from per-key tokens via `pricing.py`, so
  keep prices current. (Anthropic's cost endpoint groups by workspace, not key.)
- Admin APIs are org-level and not available on individual accounts.
- Groq and Gemini have no per-key usage API — if you want those, self-log them
  with `usage_tracker.py` (separate table) and we can merge the views.

---

## New features (v2)

### 1. Export
At the bottom of the dashboard: download per-key CSV, per-model CSV, or an
"Everything" Excel workbook (per-key + per-model + raw filtered rows).
Needs `pip install openpyxl` for the Excel button.

### 2. Auto-refresh (Windows Task Scheduler)
`fetch_usage.py` is what refreshes data. To run it automatically:
1. Edit `refresh.bat` so the path matches your project folder.
2. Open **Task Scheduler** → Create Basic Task.
3. Trigger: Daily (pick a time, e.g. 7:00 AM).
4. Action: Start a program → browse to `refresh.bat`.
5. Finish. It now pulls fresh data daily and writes `refresh.log`.

(Your `.env` admin keys are read automatically, so the scheduled run
authenticates without any manual step.)

### 3. Cost-spike detection
A key is flagged when its latest-day cost exceeds `multiplier` × its average
over the prior `lookback_days` (defaults: 3× over 7 days, and > $1).
Shown in the "Cost Spikes Detected" section. Tune in `config.json`.

### 4. Idle / unused keys
Lists keys with zero usage in the selected date range — cleanup candidates.

(Budget-based remaining credits and Slack alerts were removed — neither
OpenAI nor Anthropic exposes a real account-balance API, so that feature
couldn't be made reliable.)