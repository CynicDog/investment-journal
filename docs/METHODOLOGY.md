# Methodology

How the system is wired. If you change the math, the schemas, or the workflow shape, update this file.

## Source-of-truth files

| File / dir | Hand-edited? | Edited by automation? |
|---|---|---|
| `pyproject.toml`, `uv.lock` | Yes | Locked by CI |
| `src/investment_journal/` | Yes (DSL evolution) | No |
| `portfolio/allocation.yml` | Yes (rare, deliberate) | No |
| `portfolio/positions/*.md` | Yes (thesis prose) | Yes (only the `<!-- news-start --> ... <!-- news-end -->` block, by weekly review) |
| `portfolio/dashboards/dca-flow.md` | **No** — fully regenerated | `scripts/render_dashboards.py` |
| `risks/R-*.md` | **No** — file via `scripts/file_a_risk.py`; resolution = direct edit + push | `scripts/file_a_risk.py` (writes new); user edits status to `resolved` |
| `risks/.index_body.md` | **No** | Transient; `scripts/render_risks_index.py` writes-then-deletes |
| `README.md` | Yes | No |

## DSL contract

`src/investment_journal/` is the single source of truth for the *shape* of every artifact the repo produces. Two halves:

- `models/` — Pydantic models that validate inputs (yaml, dossier markdown).
- `render/` — pure functions that turn validated models into markdown for issue bodies + dashboards.

Workflows that author content (`weekly-review.yml`, `earnings-watcher.yml`, `earnings-recap.yml`, `thesis-review.yml`, `risks-index-sync.yml`, `update-dashboards.yml`) load the DSL via `uv sync --frozen` and either:
- call a renderer directly (deterministic case — dashboards, risks index), or
- emit markdown that **must conform to the model's documented shape** (Claude case — weekly review, earnings recap). Doc anchors in `docs/PROMPTS.md` instruct Claude on the shape, but they don't yet validate Claude's output.

`tests/test_models.py` smoke-tests every model and every renderer.

## Risks lifecycle

1. **Surface**: a weekly review or earnings watcher decides a concern is thesis-impacting.
2. **File**: `scripts/file_a_risk.py` is invoked with `--title --severity --surfaced-in --description --monitor-for` (and optional `--ticker`). It:
   - Picks the next free `R-YYYY-MM-NNN` id (current month, increment by file count).
   - Validates a `Risk` model.
   - Writes `risks/R-YYYY-MM-NNN.md`.
   - `gh issue create --label risk` with body rendered by `render_risk_issue`.
   - Back-fills `issue_number` into the file's frontmatter.
3. **Track in the parent review**: the parent issue body's `## Risks` section lists `- [ ] #<issue_number> — <title>` per filed risk. When the child issue closes, the checkbox auto-renders as ticked in GitHub's UI.
4. **Discuss**: ongoing discussion happens in the per-risk issue.
5. **Resolve**: a human edits `risks/<id>.md` to `status: resolved` + adds `resolved_on` + `resolution_note`, pushes. The push triggers `risks-index-sync.yml`, which:
   - Re-renders the pinned Risks Index issue body (resolved risks move to the "Recently resolved" table).
   - Closes the corresponding child issue.
6. The markdown file is **never deleted**. Resolved entries stay in `risks/` for history; the Risks Index only displays the 10 most recently resolved.

## Dashboards

`scripts/render_dashboards.py` reads `allocation.yml` via the DSL and writes `portfolio/dashboards/dca-flow.md` — a sankey-beta diagram grouped by sector (`Daily $X → sector → ticker`). That's the only file it writes.

`portfolio/dashboards/upcoming-earnings.md` is owned by `earnings-watcher.yml`, not the renderer. There is no allocation pie, no drift table, no market-value math. Allocation drift is observed visually at Toss.

## Workflow contracts

| Workflow | Trigger | Reads | Writes |
|---|---|---|---|
| `update-dashboards.yml` | push to `portfolio/**` or `scripts/render_dashboards.py` | `allocation.yml` | `dashboards/dca-flow.md`, commits if changed |
| `thesis-review.yml` | 1st of month 22 UTC + dispatch | `allocation.yml`, existing thesis-review issues | one issue per ticker for the just-completed month (idempotent) |
| `weekly-review.yml` | Fri 21:30 UTC + dispatch | full repo + open risk issues + web | new weekly-review issue; new `risks/R-*.md` files (committed by the workflow) |
| `earnings-watcher.yml` | daily 13 UTC + dispatch | tickers + open earnings issues + open risk issues + web | new pre-call earnings issues; `dashboards/upcoming-earnings.md`; optionally `risks/R-*.md` |
| `earnings-recap.yml` | daily 13:30 UTC + dispatch | open earnings issues past their date + web | `### Recap` comment on the issue; ticks `Earnings released` / `Recap published`; optionally `risks/R-*.md` |
| `risks-index-sync.yml` | push to `risks/R-*.md` + dispatch | all `risks/R-*.md` | Risks Index issue body (creates+pins on first run) |
| `claude-mention.yml` | `@claude` in issue/PR | as Claude reads | issue/PR comments |
| `issue-checkbox-tick.yml` | edit/comment on `auto-tick`-labeled issue | issue body | flipped `[ ] → [x]`, one summary comment |

## What we explicitly do not do

- Cost-basis tracking, share-count tracking, real P&L. Toss is the source of truth for actual holdings; we don't try to mirror it.
- Live price feeds, market-value drift, P&L curves.
- Tax lot accounting (FIFO/LIFO/specific ID).
- Currency conversion (KRW ↔ USD).
- Broker-side automation (placing orders).

If Toss exposes an API in the future, layering cost-basis tracking on top is straightforward: add a `Trade` model + a `trades.yml` (or csv), restore drift math, regenerate the dashboard. The DSL / split between deterministic renderers and Claude-narrated commentary stays.
