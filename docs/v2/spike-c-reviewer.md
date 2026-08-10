# Spike C — Local Reviewer Quality

## Fixtures

`tests/fixtures/review/*.json` — one case each:

- `good_article`
- `generic_fallback`
- `headline_repetition`
- `weak_why_watch`
- `entity_corruption`
- `unsupported_interpretation`

## Eval

```bash
# Deterministic + rubric (no LLM required for gate checks)
uv run python -m unittest tests.test_editorial_review -v

# Optional live Ollama (when daemon up)
REVIEW_SPIKE_LIVE=1 uv run python scripts/spikes/review_bench.py
```

## Approach order (if quality insufficient)

1. Prompt / rubric
2. Strengthen deterministic validator
3. Model change

## Results (2026-08-10)

| Fixture suite | 6/6 deterministic decisions matched |
| Live Ollama | not run (daemon unavailable in agent environment) |
| Next | `REVIEW_SPIKE_LIVE=1 uv run python scripts/spikes/review_bench.py` on M2 with model loaded |
