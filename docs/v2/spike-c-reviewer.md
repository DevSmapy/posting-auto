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

Do **not** switch to Cloud LLM.

## Results

| Date | Fixture suite | Live Ollama | Notes |
|------|---------------|-------------|-------|
| 2026-08-10 | 6/6 deterministic OK | not run | agent env |
| 2026-08-11 | — | **deferred** | Ollama daemon down (`:11434` refused) during rollout agent session |

### Operator — Wave 1 (run locally when Ollama is up)

```bash
# fixture bench with LLM
REVIEW_SPIKE_LIVE=1 uv run python scripts/spikes/review_bench.py

# autonomous dry + LLM reviewer; then open editorial_report.md
MVP_MODE=autonomous AUTO_PUBLISH=false NOTIFY_CHANNEL=auto \
  EDITORIAL_LLM_REVIEWER=1 \
  uv run python scripts/mvp_pipeline.py
# → output/<run>/attempts/content-01/editorial_report.md
```
