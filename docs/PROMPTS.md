# Prompts

Centralized prompt library for the Claude-driven workflows. Each anchor below is referenced by name from the corresponding workflow yaml. Edit a prompt here and the next workflow run picks it up — no yaml change needed.

> Tone (always): terse, factual, present tense; no predictions; no advice language; cite primary sources inline. End top-level issue bodies with `_Personal journal. Not financial advice._`.

The DSL contract (Pydantic schemas + renderers) lives in `src/investment_journal/`. When in doubt about the shape of a thing you're about to emit, read the model.

---

## weekly-review

Inputs you must read before writing anything:

- `portfolio/allocation.yml` — target weights, DCA per ticker.
- `portfolio/positions/*.md` — full dossiers.
- `portfolio/dashboards/dca-flow.md` — already refreshed by the workflow before you ran.
- Open `risk` issues (so you don't duplicate-file an existing one):
  ```bash
  gh issue list --label risk --state open --limit 30 --json number,title,body
  ```

Then web-search the last 7 days of news per ticker. Source priority:
1. Company press release (IR site)
2. SEC 8-K / 10-Q / 10-K
3. Earnings call transcripts
4. Reputable trade press (last resort, must cite)

### Risks step (do this BEFORE composing the review body)

For every NEW concern you'd consider thesis-impacting (i.e. a thing the user should monitor for resolution), call:

```bash
uv run python scripts/file_a_risk.py \
  --title "<one-line, < 120 chars>" \
  --severity low|medium|high \
  --surfaced-in "weekly-review/${WEEK_TAG}" \
  --ticker "<TICKER>"          # omit for portfolio-level risks
  --description "<2–4 sentences with citation>" \
  --monitor-for "<concrete signals that would resolve this>"
```

The script writes `risks/<id>.md`, opens a child issue (label `risk`), and prints one JSON line:
```json
{"id":"R-2026-04-001","issue_number":23,"path":"risks/R-2026-04-001.md","url":"https://..."}
```

Capture the `id` and `issue_number` for the next step. Do NOT file a risk that duplicates an already-open one — check the open-risk list first.

### Issue body shape

Open the weekly review issue:
```bash
gh issue create --title "Weekly review ${WEEK_TAG}" --label weekly-review --body-file <file>
```

Body must follow this shape (mirrors `WeeklyReview` + `render_weekly_review`):

```markdown
# Weekly review {ISO-week}

_Generated {YYYY-MM-DD}._

## Per-position update

### {TICKER}

**News (last 7d):**

- {bullet} ([source](url))
- ...

**Valuation read:** {one line, e.g. "Fwd P/E ~Xx vs 5y avg ~Yx ([source](url))".}

**Thesis status:** `still-holds` | `monitor` | `re-check-needed` — {one sentence why}.

---

(repeat per ticker)

## Catalyst calendar (next 30 days)

- {YYYY-MM-DD}: **{TICKER}** — {event} — {issue link if any}
- ...

## Risks

**Surfaced this week:**

- [ ] #{issue_number} — {risk title}      <!-- one per filed risk -->

**Resolved this week:**

- ~~#{issue_number}~~ — {risk title}      <!-- if any closed since last review -->

(If neither applies, write: `_No risk changes this week._`.)

---

_Personal journal. Not financial advice._
```

### Constraints

- Do NOT modify position dossiers, `allocation.yml`, or any auto-rendered dashboard.
- New `risks/R-*.md` files are the only repo writes you should produce. The workflow commits them after you finish.
- If you cannot find a primary source for a number, mark it `(unverified)`.
- If you cannot confirm a risk is real, do not file it. Conservative beats noisy.

## thesis-review

Monthly red-team of each position's thesis. The point is **stress-testing**, not affirmation — challenge bull-case bullets against current data, strengthen bear-case bullets where new evidence supports it, and surface concerns the user might rationalise away. Final verdict still belongs to the user; your job is to put the strongest case against each thesis on the table.

Inputs you must read per ticker, before composing anything:

- `portfolio/allocation.yml` — target weight + DCA size (concentration risk reads differently at 25% vs 5%).
- `portfolio/positions/<TICKER>.md` — full dossier: current thesis, bull / bear bullets, valuation snapshot, recent earnings table, news log inside `<!-- news-start --> ... <!-- news-end -->`.
- Recent weekly-review issues (last ~6 weeks):
  ```bash
  gh issue list --label weekly-review --state all --limit 6 --json number,title,body,closedAt
  ```
- Last 1–2 earnings recaps for the ticker (closed `earnings` issues filtered to the ticker; read the `### Recap` comment).
- Open `risk` issues — so you don't duplicate-file an existing concern:
  ```bash
  gh issue list --label risk --state open --limit 50 --json number,title,body
  ```

Then web-search the last 30 days of news per ticker. Source priority (same as weekly review):
1. Company press release (IR site)
2. SEC 8-K / 10-Q / 10-K
3. Earnings call transcripts
4. Reputable trade press (last resort, must cite)

### Red-team checklist (work through this for each ticker)

For each bull-case bullet in the dossier, ask:
- Is the supporting data still current? (revenue trajectory, margin trend, market share, guidance.)
- Has a competitor, regulator, or counterparty done something that erodes it?
- Is the valuation premise (multiple, FCF yield, growth rate) still defensible vs. peers and history?

For the bear case, ask:
- Has any listed risk materialised partially or in full since the dossier was last reviewed?
- Is there a new bear bullet the dossier is missing? (Concentration, customer churn, regulatory action, key-person, supply chain, balance sheet.)

For capital allocation:
- Buyback pace, dividend coverage, insider buying / selling — anything signalling management confidence shift?

For valuation:
- Where does the current multiple sit vs. the dossier's `Valuation snapshot` table? Flag mean-reversion risk if the gap widened.

### Risk filing (do this BEFORE composing the issue body)

For every NEW thesis-impacting concern (not already an open risk), file one:

```bash
uv run python scripts/file_a_risk.py \
  --title "<one-line, < 120 chars>" \
  --severity low|medium|high \
  --surfaced-in "thesis-review/<TICKER>-<YYYY-MM>" \
  --ticker "<TICKER>" \
  --description "<2–4 sentences with citation>" \
  --monitor-for "<concrete signals that would resolve this>"
```

Capture the printed JSON ids; reference them in the issue body's Risks section. Do not file speculative or low-conviction risks here — if you wouldn't bet a position on it, don't file it.

### Issue body shape

Build via the DSL — do not hand-format:

```bash
uv run python - <<'PY' > /tmp/body.md
from investment_journal import Risk, ThesisReview
from investment_journal.render import render_thesis_review

tr = ThesisReview(
    ticker="<TICKER>",
    month="<YYYY-MM>",
    verdict="still-holds" | "partially" | "no",
    verdict_note="<one sentence justifying the verdict>",
    bull_changes="<markdown bullets — what data weakened or strengthened the bull case>",
    bear_changes="<markdown bullets — what data strengthened the bear case>",
    action="pending human confirmation — see red-team analysis",
    risks_surfaced=["R-YYYY-MM-NNN", ...],
)
risks_lookup = { ... }  # build from filed-risk JSON
print(render_thesis_review(tr, risks_lookup))
PY
gh issue create --title "Thesis review: <TICKER> <YYYY-MM>" \
                --label thesis-review --body-file /tmp/body.md
```

Verdict policy:
- `still-holds` — only if no material change since last review and no new risk surfaced.
- `partially` — default whenever any bullet is challenged by new data, even if directionally the thesis survives.
- `no` — only if the original premise has been contradicted (e.g. moat eroded, guidance reset, fraud).

`action` belongs to the user — leave it as `"pending human confirmation — see red-team analysis"` unless the data unambiguously implies a mechanical action (e.g. "trim — weight drift > 3pp from target").

### Constraints

- Do NOT modify position dossiers, `allocation.yml`, or any auto-rendered dashboard.
- New `risks/R-*.md` files are the only repo writes you should produce. The workflow commits them after you finish.
- One issue per ticker per month. The workflow precomputes pending tickers in `$PENDING_TICKERS`; process only those.
- If you cannot find a primary source for a number, mark it `(unverified)`.
- If you cannot confirm a risk is real, do not file it. Conservative beats noisy.
- Cite every claim. A red-team review without sources is just opinion.

---

## earnings-watcher

Pre-call only. Post-call recaps are authored by `## earnings-recap` (a separate workflow).

Inputs:
- `portfolio/allocation.yml`
- Open earnings issues: `gh issue list --label earnings --state open`
- Open risk issues (to avoid duplicates): `gh issue list --label risk --state open`

Loop per ticker. For each:

1. Web-search the next confirmed earnings date. Trust order: company IR site > NASDAQ earnings calendar > broker page. Aggregators are unreliable — do not date from them.
2. If no primary-source confirmation, skip this ticker for the run.
3. **Open the pre-call issue**: if the date is within 7 days AND no open issue with title matching `Earnings: {TICKER} {QQ}{YY}` exists:
   - Compute the quarter label (`1Q26` for Jan–Mar 2026).
   - Open an issue with title `Earnings: {TICKER} {QQ}{YY}`, labels `earnings,auto-tick`. Body must mirror the `EarningsEvent` shape (header date + `## Tracking checklist` + optional `## Prep notes`).
4. **Risk filing (prep stage)**: if writing prep notes surfaces a material thesis-impacting concern that is NOT already an open risk (e.g. guidance reset signals from peer prints, supply-chain alerts), file one with `--surfaced-in "earnings/<TICKER>-<QQYY>"`. Do not file speculative or low-conviction risks here.

Be conservative. Skip a day rather than publish a wrong date.

---

## earnings-recap

Post-call only. Recap lives as a comment on the existing earnings issue (the body itself stays canonical to `render_earnings_event`'s output; only the tracking checklist gets ticked).

Inputs:
- Open earnings issues: `gh issue list --label earnings --state open --json number,title,body`
- If env var `ISSUE_NUMBER` is set (manual dispatch), scope to just that issue and skip the date-window filter.
- Otherwise, filter to issues whose `Expected: **YYYY-MM-DD**` line is in the past 0–3 days.
- Open risk issues (to avoid duplicates): `gh issue list --label risk --state open`

For each in-scope issue:

1. **Idempotency check**: `gh issue view <N> --comments`. If any existing comment contains a line starting with `### Recap`, skip this issue entirely. Do not post a second recap.
2. Web-search the press release + earnings call transcript. Trust order: company IR site / 8-K > earnings call transcript host (Motley Fool, Seeking Alpha) > reputable trade press. If the transcript is not yet available, post a partial recap based on the press release alone and add `_transcript pending_` on its own line at the end.
3. **Post the recap comment** with shape:
   ```markdown
   ### Recap

   - **Reported:** rev $X.XXB ({+/-X% YoY}); EPS $X.XX (cite source).
   - **Guidance:** raised | reiterated | lowered — {quoted line}.
   - **Call quotes:**
     - > {short verbatim line that moves the thesis}
   - **Thesis impact:** pending human review.
   - **Sources:** [press release](url), [transcript](url)
   ```
4. **Tick the body checkboxes**: `gh issue edit <N> --body-file <new>` to flip `[ ] Earnings released` → `[x]` and `[ ] Recap published` → `[x]`. Preserve every other byte of the body, including the other three checklist items (`Prep notes written`, `Thesis-impact assessed`, `Position dossier updated`) — those are subjective and stay for human review.
5. **Risk filing (post-call)**: if the recap reveals a material thesis-impacting concern that is NOT already an open risk, file one with `--surfaced-in "earnings/<TICKER>-<QQYY>"`. Do not file speculative or low-conviction risks here.

Be conservative. Skip a day rather than publish wrong numbers.

---

## issue-checkbox-tick

You are reviewing one issue (`$ISSUE_NUMBER`). Goal: tick `[ ] → [x]` only for items that are objectively verifiable.

Hard rules:

- **Never tick subjective items.** Examples: "Thesis-impact assessed", "Action taken", "Allocation in line with target", anything requiring human judgment.
- **Never untick** (`[x] → [ ]`).
- **Never edit any file.** This workflow only edits issue text.
- **Never tick more than 5 items in a single run.** If more qualify, tick the first 5 and note the cap in your comment.

Steps:

1. `gh issue view "$ISSUE_NUMBER" --json body,title,labels,comments`.
2. For each `- [ ]` line, classify auto-tickable vs subjective:
   - `[ ] Earnings released` — verifiable if earnings date in body has passed AND a primary press release exists.
   - `[ ] Recap published` — verifiable if a comment with `### Recap` exists on the issue.
   - `[ ] 10-Q filed` — verifiable from SEC EDGAR.
4. For each auto-tickable item, build the new body (preserving everything else byte-for-byte) and `gh issue edit "$ISSUE_NUMBER" --body-file <new>`.
5. Post ONE comment listing what you ticked and the citation:
   ```
   Auto-ticked:
   - `[x] Earnings released` — confirmed by press release dated 2026-05-06: <url>
   - `[x] Recap published` — comment #N has `### Recap`.
   Left untouched: `[ ] Thesis-impact assessed` (subjective).
   ```
6. If nothing is verifiable, post nothing. Exit silently.

---

## watchlist-screen

Monthly quality screen of all `watching` and `priority` candidates in `portfolio/watchlist.yml`.
Uses the quantitative threshold set in `investment_journal.models.screener.THRESHOLDS`.

The goal is to answer: **does this candidate pass the quality bar?** If all four buckets pass,
flag it as `ready` — human still decides whether to add to portfolio.

### Inputs

```bash
# Read the current watchlist
cat portfolio/watchlist.yml
# Read current open watchlist issues (to comment on if a candidate upgrades)
gh issue list --label watchlist --state open --json number,title,body
```

### For each candidate (status: watching or priority)

1. **Fetch metrics and run screen** via the dedicated script — no web crawling needed:
   ```bash
   uv run python scripts/screen_candidate.py --ticker <TICKER>
   ```
   This calls Alpha Vantage (5 endpoints: OVERVIEW, BALANCE_SHEET, INCOME_STATEMENT,
   CASH_FLOW, EARNINGS) using `ALPHA_VANTAGE_API_KEY_2` from env, computes all 10 metrics,
   runs `score_candidate()`, and prints one JSON line:
   ```json
   {
     "ticker": "MSFT",
     "fetched_on": "2026-05-03",
     "metrics": {"fcf_yield_pct": 2.3, ...},
     "screen_results": [{"bucket": "cash", "passed": true, "note": "..."}, ...]
   }
   ```
   If the script exits non-zero (e.g. ticker not found, AV error), skip that candidate
   and print a warning — do not halt the whole run.

2. **Update `portfolio/watchlist.yml`** — replace the `screen_results` list for this entry with
   the `screen_results` array from the JSON output. Preserve all other fields.
   Also set `status` to `priority` if all 4 buckets pass and it was previously `watching`.

4. **If all 4 buckets now pass** and the candidate has an open `watchlist` issue, post a comment:
   ```
   Quality screen updated (YYYY-MM-DD): all 4 buckets now pass.
   Metrics: <bullet per bucket with note>.
   Ready for portfolio consideration.
   ```

### Commit

After updating all candidates:
```bash
git add portfolio/watchlist.yml
git commit -m "chore(watchlist): refresh quality screen (run #${RUN_ID})"
git push
```

### Constraints

- Do NOT change conviction or status to `added-to-portfolio`. That is a human decision.
- If no primary-source metric data is available for a candidate, skip that candidate for this run
  and note it in stdout (do not write half-screened results).
- Do NOT screen candidates with status `parked` or `added-to-portfolio`.
- If `watchlist.yml` is empty, print "watchlist is empty — nothing to screen" and exit cleanly.

---

## horizon-review

Annual phase gate review. Reads the current phase from `portfolio/horizon_plan.yml`,
loads all scenarios, and opens a `horizon-review` issue.

### Inputs

```bash
# Read the horizon plan
cat portfolio/horizon_plan.yml
# Load all scenarios
ls portfolio/scenarios/S-*.md 2>/dev/null || echo "(none yet)"
# Read open watchlist issues
gh issue list --label watchlist --state open --json number,title
# Read open scenario issues
gh issue list --label scenario --state open --json number,title,body
```

### Compose the review issue

Use the DSL:

```bash
uv run python - <<'PY' > /tmp/horizon_body.md
from investment_journal import HorizonPlan, Scenario
from investment_journal.render import render_horizon_review
from pathlib import Path

plan = HorizonPlan.load("portfolio/horizon_plan.yml")
scenarios = Scenario.load_all(Path("portfolio/scenarios"))
print(render_horizon_review(plan, scenarios))
PY
gh issue create \
  --title "Horizon review — Phase $(uv run python -c "from investment_journal import HorizonPlan; p=HorizonPlan.load('portfolio/horizon_plan.yml'); print(p.current_phase.phase)"): $(uv run python -c "from investment_journal import HorizonPlan; p=HorizonPlan.load('portfolio/horizon_plan.yml'); print(p.current_phase.name)")" \
  --label horizon-review \
  --body-file /tmp/horizon_body.md
```

### Decision gate analysis

For each unanswered gate in the current phase, provide a brief analysis (2–4 sentences)
based on reading the available dossiers, scenarios, and recent weekly reviews. Add the
analysis as a comment on the newly created issue immediately after opening it.

Read the last 4 weekly reviews for context:
```bash
gh issue list --label weekly-review --state closed --limit 4 --json number,title,body,closedAt
```

### Constraints

- Do NOT mark any decision gate as `answered` in `horizon_plan.yml`. That is a human decision
  after reading the issue.
- Do NOT close or resolve any scenario. That is a human decision.
- Do NOT suggest specific buy/sell/hold actions. Surface data; judgment belongs to the user.
- One issue per annual cycle. Check for existing open `horizon-review` issues first:
  ```bash
  gh issue list --label horizon-review --state open --json number,title
  ```
  If one already exists, add a comment to it instead of opening a new one.

---

## Style guide for any issue or comment you author

- Headlines: `## H2` for sections, `### H3` for sub.
- Tables for any 3+ row data set.
- Inline citations: `[source](url)` immediately after the claim.
- Numbers: include units (USD/%) and the period (TTM, YoY, QoQ).
- Footer when authoring a top-level issue body: `_Personal journal. Not financial advice._`.
