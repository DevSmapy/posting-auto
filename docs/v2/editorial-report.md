# Editorial report (md + json)

When `run_editorial_loop(..., run_dir=...)` is given a non-`None` `run_dir`, that directory gets:

| File | Audience |
|------|----------|
| `editorial_result.json` | Machine / tests |
| `editorial_report.md` | Human — Verdict, Per-story, Revision history |

If `run_dir` is omitted (`None`), neither file is written — callers only get the in-memory result dict. Direct/unit-test callers without a run directory should not expect artifacts on disk.

No Streamlit/UI. After `MVP_MODE=autonomous` (which passes a run/attempt dir), open the markdown in that folder.

Example path: `output/<run_id>/attempts/content-01/editorial_report.md`
