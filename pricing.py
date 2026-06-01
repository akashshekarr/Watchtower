"""
Per-million-token pricing (USD). Update these as prices change.
Format: provider -> model -> (input_per_million, output_per_million)
Prices are illustrative — VERIFY against each provider's current pricing page.
"""

PRICING = {
    "openai": {
        "gpt-4o":        (2.50, 10.00),
        "gpt-4o-mini":   (0.15, 0.60),
        "gpt-4.1":       (2.00, 8.00),
        "o3":            (2.00, 8.00),
        "_default":      (2.50, 10.00),
    },
    "anthropic": {
        "claude-opus-4":    (15.00, 75.00),
        "claude-sonnet-4":  (3.00, 15.00),
        "claude-haiku-4":   (1.00, 5.00),
        "_default":         (3.00, 15.00),
    },
    "gemini": {
        "gemini-2.5-pro":   (1.25, 10.00),
        "gemini-2.5-flash": (0.30, 2.50),
        "_default":         (0.30, 2.50),
    },
    "groq": {
        "llama-3.3-70b":    (0.59, 0.79),
        "llama-3.1-8b":     (0.05, 0.08),
        "_default":         (0.59, 0.79),
    },
}


def cost_for(provider: str, model: str, in_tok: int, out_tok: int) -> float:
    table = PRICING.get(provider, {})
    rate = table.get(model) or table.get("_default", (0.0, 0.0))
    return (in_tok / 1_000_000) * rate[0] + (out_tok / 1_000_000) * rate[1]