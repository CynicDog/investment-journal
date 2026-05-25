# CLAUDE.md — repo guide for Claude

This file is read on every Claude Code or Claude GitHub Action invocation. Read it before doing anything.

## What this repo is

A personal portfolio journal for an investor who DCAs daily at **Toss** (a Korean broker that exposes no trade-history API). Workflows track:

- **Intent** — target weights + per-ticker daily DCA $ in `portfolio/allocation.yml`.
- **Theses & events** — per-position dossiers, monthly thesis review issues, per-quarter earnings issues, weekly review issues.
- **Risks** — every concern surfaced in a review becomes a versioned `risks/R-*.md` file plus a child discussion issue. A pinned `Risks Index` issue aggregates all open risks.

Not a brokerage account. Not financial advice.

## DSL (you must read and use it)

Everything the repo produces has a Pydantic schema in `src/investment_journal/`. Models:

| Model | File | Purpose |
|---|---|---|
| `Allocation`, `Position`, `DCA` | `models/allocation.py` | Validates `portfolio/allocation.yml`. Enforces weights sum to 100 and per-position DCA sums to total. Position has optional `dividend_yield_pct` + `div_frequency` fields. |
| `Dossier` | `models/dossier.py` | Header + required-sections validator over `portfolio/positions/*.md`. Prose stays freeform markdown. |
| `Risk`, `Severity`, `RiskStatus` | `models/risk.py` | One markdown file per risk under `risks/<id>.md` (yaml frontmatter + body). Resolved risks must carry `resolved_on` + `resolution_note`. |
| `WeeklyReview`, `PositionUpdate`, `Catalyst`, `ThesisStatus` | `models/weekly_review.py` | Shape of a weekly review issue body. |
| `ThesisReview`, `ThesisVerdict` | `models/thesis_review.py` | Shape of a monthly thesis review issue body. |
| `EarningsEvent`, `EarningsRecap` | `models/earnings_event.py` | Shape of an earnings issue (pre-call prep + post-call recap). |
| `Tone`, `TONE_RULES`, `DISCLAIMER` | `models/tone.py` | Codified tone rules. Always append `DISCLAIMER` to top-level issue bodies. |
| `WatchlistEntry`, `ScreenResult`, `Watchlist` | `models/watchlist.py` | Quality-screened candidates in `portfolio/watchlist.yml`. Four buckets: cash, finance, stability, profitability. |
| `Scenario`, `TriggerType`, `ScenarioStatus` | `models/scenario.py` | If-then decision rules under `portfolio/scenarios/S-*.md`. Filed via `scripts/file_a_scenario.py`. |
| `HorizonPlan`, `HorizonPhase`, `DecisionGate` | `models/horizon.py` | 3-year roadmap in `portfolio/horizon_plan.yml`. Phases + decision gates. |
| `THRESHOLDS`, `score_candidate`, `metric_keys` | `models/screener.py` | Quantitative thresholds for all 4 quality buckets. Used by `watchlist-screen.yml` to auto-score candidates. |

Renderers (`src/investment_journal/render/`) turn models into markdown:

```python
from investment_journal import Risk, WeeklyReview
from investment_journal.render import render_risk_issue, render_weekly_review

# Build a model, render, post
body = render_weekly_review(my_weekly_review, risks_lookup={r.id: r for r in all_risks})
```

When in doubt: `uv run python -c "from investment_journal import <Thing>; help(<Thing>)"`.

## Filing a scenario

**Never write `portfolio/scenarios/S-*.md` by hand from a workflow.** Use the helper:

```bash
uv run python scripts/file_a_scenario.py \
  --title "Close P if no AI data infra evidence by 12 months" \
  --trigger-type time-gate \
  --ticker P \
  --trigger "At the 12-month mark (2027-05-03), P has not disclosed material AI data infra revenue." \
  --action "Halt DCA into P; run close_position.py; redistribute $8/day to highest-conviction position." \
  --context "P was added as speculative 8% on the AI data infra thesis pivot."
```

The script picks the next free `S-YYYY-MM-NNN` id, writes `portfolio/scenarios/<id>.md`, opens a child issue (label `scenario`), back-fills the issue number, and prints JSON to stdout.

## Filing a risk

**Never write `risks/R-*.md` by hand from a workflow.** Use the helper:

```bash
uv run python scripts/file_a_risk.py \
  --title "HALO single-deal dependency on Vertex Hypercon expansion" \
  --severity medium \
  --surfaced-in "weekly-review/2026-W17" \
  --ticker HALO \
  --description "The 2026-04-07 Vertex deal concentrates near-term Hypercon royalty growth on a single counterparty's program execution." \
  --monitor-for "Vertex Phase II/III readouts on Hypercon-formulated assets; additional Hypercon licensee announcements."
```

The script picks the next free `R-YYYY-MM-NNN` id, writes `risks/<id>.md` (frontmatter + body), opens a child issue (label `risk`), back-fills the issue number into the file, and prints `{"id":"...","issue_number":N,...}` JSON to stdout. Reference the id in the parent review issue's Risks section so it shows up linked.

The workflow that called Claude (`weekly-review.yml`, `earnings-watcher.yml`) commits + pushes the new markdown file after Claude finishes, then runs `scripts/render_risks_index.py` inline to refresh the pinned **Risks Index** issue body.

## Layout

| Path | What it is | Who writes it |
|---|---|---|
| `pyproject.toml` / `uv.lock` | Project metadata + lockfile (uv) | User; locked by CI |
| `src/investment_journal/` | Pydantic DSL + renderers | User |
| `tests/test_models.py` | Smoke tests | User |
| `portfolio/allocation.yml` | Target weights + DCA $ | User only (rare) |
| `portfolio/positions/*.md` | Per-ticker dossier (thesis prose) | User + weekly review may append to `<!-- news-start --> ... <!-- news-end -->` block |
| `portfolio/watchlist.yml` | Quality-screened candidates | User edits; `watchlist-screen.yml` updates `screen_results` |
| `portfolio/horizon_plan.yml` | 3-year horizon phases + decision gates | User edits; never auto-written |
| `portfolio/scenarios/S-*.md` | Decision scenarios (if-then rules) | `scripts/file_a_scenario.py` (Claude or human) |
| `portfolio/dashboards/dca-flow.md` | Sankey, regenerated | `scripts/render_dashboards.py` only |
| `risks/R-*.md` | Risk records (one per risk) | `scripts/file_a_risk.py` (Claude or human) |
| `risks/README.md` | Format + lifecycle of risks | User |
| `docs/PROMPTS.md` | Centralized Claude prompts | User |
| `docs/METHODOLOGY.md` | How the system works | User |
| `README.md` | Front page | User |

## Tone for any output you produce

- Terse, factual, present tense. Bullets over paragraphs.
- No predictions ("X will…"). Frame as "as of {date}, X is reported / disclosed / expected per company guidance / consensus".
- No advice language. No "should buy / sell / recommend".
- Cite primary sources inline (10-K, 10-Q, 8-K, IR press release, transcript). Aggregator articles are last resort.
- Numbers: include unit (USD/%) and period (TTM, YoY, QoQ).
- If a number disagrees across sources, list both and flag the discrepancy.
- End every top-level issue body you author with `_Personal journal. Not financial advice._` (or import `DISCLAIMER` from the DSL).

## Issue labels

- `position` — per-ticker dossier discussion (currently unpinned by user choice)
- `weekly-review` — weekly review reports
- `earnings` — per-quarter earnings tracking
- `thesis-review` — monthly thesis re-check (one per ticker per month)
- `risk` — child discussion issue for one risk record (canonical state in `risks/<id>.md`)
- `risks-index` — the single pinned Risks Index issue
- `auto-tick` — eligible for `[ ]→[x]` automation by `issue-checkbox-tick.yml`
- `watchlist` — per-candidate discussion issue (one per `WatchlistEntry`)
- `scenario` — per-scenario tracking issue (canonical state in `portfolio/scenarios/S-*.md`)
- `horizon-review` — annual phase gate review issue (opened by `horizon-review.yml`)

## What you must never do

1. **Never edit `risks/R-*.md` by hand from a workflow.** Use `scripts/file_a_risk.py` to file new risks; for resolution, instruct the user to set `status: resolved` + `resolved_on` + `resolution_note` and push.
2. **Never edit `portfolio/scenarios/S-*.md` by hand from a workflow.** Use `scripts/file_a_scenario.py` to file new scenarios; for status changes, instruct the user to edit and push.
3. **Never edit `portfolio/allocation.yml`** unless the user explicitly states the new weights in the same turn.
4. **Never write `portfolio/dashboards/dca-flow.md` by hand.** It's regenerated by `scripts/render_dashboards.py`.
5. **Never push prices, EPS, or forecasts as facts** without citing the source. If you can't cite, mark `(unverified)`.
6. **Never close `position` issues.** Pinned dossiers, open indefinitely.
7. **Never modify `README.md`** unless explicitly asked.
8. **Never bypass the DSL.** Build a model and render with the supplied renderer rather than emitting hand-formatted markdown that mimics the schema.
9. **Never mark `horizon_plan.yml` decision gates as answered**, resolve scenarios, or change watchlist status to `added-to-portfolio` — all of those are human decisions.

## Useful commands

```bash
# Re-render the sankey dashboard
uv run python scripts/render_dashboards.py

# Regenerate the Risks Index issue body
uv run python scripts/render_risks_index.py

# Validate every dossier + allocation
uv run pytest -q

# Run all DSL smoke tests
uv run pytest tests/

# List open weekly reviews
gh issue list --label weekly-review --state open

# File a scenario (decision rule)
uv run python scripts/file_a_scenario.py --help

# Validate watchlist
uv run python -c "from investment_journal import Watchlist; Watchlist.load('portfolio/watchlist.yml'); print('ok')"

# Validate horizon plan
uv run python -c "from investment_journal import HorizonPlan; p=HorizonPlan.load('portfolio/horizon_plan.yml'); print(f'Phase {p.current_phase.phase}: {p.current_phase.name}')"

# Run quality screener against a candidate (replace metrics as needed)
uv run python -c "
from investment_journal import score_candidate
results = score_candidate({'fcf_yield_pct': 4.5, 'net_cash_ratio': 0.1, 'debt_to_equity': 0.8,
  'interest_coverage': 12.0, 'current_ratio': 1.5, 'revenue_cagr_3y_pct': 10.0,
  'earnings_beat_rate_pct': 75.0, 'gross_margin_pct': 60.0, 'roic_pct': 18.0, 'roe_pct': 22.0})
for r in results: print(r.bucket, '✓' if r.passed else '✗', r.note)
"
```

## Disclaimer

Personal journal. Positions, weights, and notes reflect personal opinion as of the date written and may be wrong, stale, or revised without notice. Not financial advice.
