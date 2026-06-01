"""
test_log.py  —  quick check that logging works.
Run:  python test_log.py
Then refresh the dashboard to see the data.
"""

from usage_tracker import UsageTracker

t = UsageTracker()

t.log("openai", key_label="oai-prod", model="gpt-4o",
      input_tokens=1200, output_tokens=350)
t.log("anthropic", key_label="claude-prod", model="claude-sonnet-4",
      input_tokens=2000, output_tokens=600)
t.log("groq", key_label="groq-1", model="llama-3.3-70b",
      input_tokens=800, output_tokens=200)

print("Logged 3 sample calls to usage.db")