# Code Style & Quality

[← Back to Standards](../README.md)

---

- Follow agreed linter config (e.g. `ruff` for Python, `eslint` for TS). No bypass without team sign-off.
- Max function length: **50 lines**. Max file length: **400 lines**.
- No commented-out code merged to `main`.
- SonarQube / code quality gate must pass before merge.

---

## Verification — 2026-05-22

Audited: `backend/app/` (15 Python files)

| # | Rule | Status | Detail |
|---|---|---|---|
| 1 | Linter config (`ruff`) | ❌ FAIL | No `ruff.toml` / `pyproject.toml`. `ruff` absent from `requirements.txt` |
| 2 | Function length ≤ 50 lines | ❌ FAIL | 2 violations (see below) |
| 3 | File length ≤ 400 lines | ✅ PASS | Largest file: `graph_engine.py` at 313 lines |
| 4 | No commented-out code | ✅ PASS | None detected |
| 5 | SonarQube / quality gate | ❌ FAIL | No `sonar-project.properties` or CI quality gate config found |

### Function length violations

| File | Function | Line | Length |
|---|---|---|---|
| [batch_pipeline.py:23](../../backend/app/batch_pipeline.py#L23) | `run_batch()` | 23 | **133 lines** |
| [graph_engine.py:78](../../backend/app/graph_engine.py#L78) | `_upsert_claim_graph()` | 78 | **71 lines** |

### Action items

- [ ] Add `ruff` to `requirements.txt` (dev deps) and create `ruff.toml` or `[tool.ruff]` in `pyproject.toml`
- [ ] Break `run_batch()` into smaller functions (133 lines → target ≤ 3 functions of ≤ 50 lines each)
- [ ] Break `_upsert_claim_graph()` into smaller functions (71 lines)
- [ ] Add SonarQube config or a CI lint/quality gate (e.g. GitHub Actions step running `ruff check .`)
