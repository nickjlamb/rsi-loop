"""Model tiers. PROVISIONAL until the freeze (M8), when the exact identifiers
are pinned in experiments/preregistration.md and nothing changes afterwards.

All models are reached through the Perplexity Agent API (providers.py), which
serves third-party models at provider rates with web search off when no tools
are requested. Identifiers as listed on the Agent API models page, 22 Sep 2026."""

DEFAULT_TIER = "anthropic/claude-sonnet-5"     # design D.4 "Sonnet-class"
STRONG_TIER = "anthropic/claude-opus-5"        # design D.4 "Opus/Fable-class"
CANDIDATE_ALTERNATIVES = ("anthropic/claude-haiku-4-5", "anthropic/claude-fable-5", "openai/gpt-5.1", "perplexity/sonar")
