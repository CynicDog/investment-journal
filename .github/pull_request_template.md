## What

<!-- 1-2 sentences. -->

## Why

<!-- The motivation. If this changes weights, paste the rationale. -->

## Files touched

- [ ] `portfolio/allocation.yml` (high-stakes — explain the new weights)
- [ ] `portfolio/positions/*.md` (thesis / catalyst / valuation update)
- [ ] `portfolio/dashboards/*.md` (auto-rendered — should not be hand-edited)
- [ ] `scripts/*` (renderer changes — verify with `python scripts/render_dashboards.py`)
- [ ] `.github/workflows/*` (smoke-tested via `workflow_dispatch`)
- [ ] `docs/*` or `CLAUDE.md`

## Verification

- [ ] `python scripts/render_dashboards.py` runs cleanly locally.
- [ ] No accidental edit inside dashboard `<!-- ... -->` auto-blocks.
