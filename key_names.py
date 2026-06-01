"""
key_names.py
------------
OPTIONAL. Maps the key IDs returned by the usage APIs to the friendly
names you see in the OpenAI / Anthropic dashboards.

The usage APIs return IDs like 'key_VVawtqwFGrCCDwvd' or
'apikey_01Rj2N8SVvo6BePZj99NhmiT', not names like "Report JSON formatting".
Fill this in (as much or as little as you want) to get readable labels.
Any ID not listed here just shows as its raw ID — nothing breaks.

Tip: the OpenAI "Tracking ID" column in your dashboard IS the key_id.
"""

KEY_NAMES = {
    # --- OpenAI (Tracking ID -> name) ---
    # "key_VVawtqwFGrCCDwvd": "Report JSON formatting (Prod)",
    # "key_FIxX2JVc0hn4soZz": "Subspeciality tagging (Prod)",

    # --- Anthropic (api_key_id -> name) ---
    # "apikey_01Rj2N8SVvo6BePZj99NhmiT": "Surgical-LLM Agent",
}


def label_for(key_id: str) -> str:
    return KEY_NAMES.get(key_id, key_id)
