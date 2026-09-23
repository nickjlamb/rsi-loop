"""One paid call to the Perplexity Agent API to confirm the key, the credits,
the model identifier and the response shape — before anything else spends.

    PERPLEXITY_API_KEY=... python3 -m optimizer.smoke --model anthropic/claude-sonnet-5

Prints the model's one-line reply, token usage, the cost the API reports, and
the top-level keys of the raw response. Sends no tools (web search off)."""

from __future__ import annotations

import argparse
import json
import os
import sys

from optimizer.providers import PerplexityAgentProvider, ProviderError


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="anthropic/claude-sonnet-5")
    ap.add_argument("--dump", action="store_true", help="print the raw response JSON")
    ap.add_argument("--sync", action="store_true", help="hold the connection open instead of background+poll")
    ap.add_argument("--reasoning", choices=["low", "medium", "high"], default=None)
    a = ap.parse_args(argv)
    key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not key:
        print("PERPLEXITY_API_KEY is not set", file=sys.stderr)
        return 2
    p = PerplexityAgentProvider(key, background=not a.sync, reasoning_effort=a.reasoning)
    msgs = [{"role": "system", "content": "Reply with exactly one short sentence."},
            {"role": "user", "content": "State the model you are and confirm you did not use web search."}]
    try:
        c = p.complete(msgs, model=a.model, max_output_tokens=200)
    except ProviderError as e:
        print("FAILED:", e, file=sys.stderr)
        return 1
    print("reply:", c.text.strip())
    print("model:", c.model, "| latency:", c.latency_s, "s")
    print("usage:", json.dumps(c.usage))
    print("cost_usd:", c.cost_usd)
    print("raw keys:", sorted((c.raw or {}).keys()))
    print("status:", (c.raw or {}).get("status"), "| background:", (c.raw or {}).get("background"), "| mode:", "sync" if a.sync else "background+poll")
    print("reasoning (echoed):", (c.raw or {}).get("reasoning"), "| requested:", a.reasoning)
    if a.dump:
        print(json.dumps(c.raw, indent=1)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
