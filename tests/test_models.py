"""Smoke tests for the DSL: every model validates and rejects malformed input."""

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from investment_journal import (
    Allocation,
    DecisionGate,
    Dossier,
    EarningsEvent,
    HorizonPhase,
    HorizonPlan,
    Risk,
    Scenario,
    ScreenResult,
    ThesisReview,
    Watchlist,
    WatchlistEntry,
    WeeklyReview,
    metric_keys,
    score_candidate,
)
from investment_journal.models.earnings_event import EarningsRecap
from investment_journal.models.weekly_review import (
    Catalyst,
    PositionUpdate,
)
from investment_journal.render import (
    render_capital_flow_sankey,
    render_earnings_event,
    render_horizon_review,
    render_risk_issue,
    render_risks_index,
    render_scenario_issue,
    render_thesis_review,
    render_watchlist_issue,
    render_weekly_review,
)


REPO = Path(__file__).resolve().parents[1]


def test_allocation_loads_real_file() -> None:
    a = Allocation.load(REPO / "portfolio" / "allocation.yml")
    assert sum(p.target_pct for p in a.positions) == pytest.approx(100.0, abs=0.01)
    assert sum(p.dca_per_day_usd for p in a.positions) == a.dca.total_per_day_usd


def test_allocation_rejects_bad_total() -> None:
    a = Allocation.load(REPO / "portfolio" / "allocation.yml")
    bad = a.model_dump(mode="python")
    bad["positions"][0]["target_pct"] = bad["positions"][0]["target_pct"] + 1
    with pytest.raises(ValidationError):
        Allocation.model_validate(bad)


def test_every_dossier_validates() -> None:
    for p in (REPO / "portfolio" / "positions").glob("[A-Z]*.md"):
        Dossier.from_file(p)


def test_risk_open_and_resolved() -> None:
    open_risk = Risk(
        id="R-2026-04-001",
        title="HALO single-deal dependency on Vertex Hypercon expansion",
        ticker="HALO",
        severity="medium",
        surfaced_in="weekly-review/2026-W17",
        surfaced_on=date(2026, 4, 26),
        description="The Vertex deal concentrates near-term Hypercon royalty growth.",
        monitor_for="Vertex Phase II/III readouts; additional Hypercon licensee announcements.",
    )
    assert open_risk.status == "open"

    resolved = open_risk.model_copy(
        update={
            "status": "resolved",
            "resolved_on": date(2026, 7, 1),
            "resolution_note": "Second Hypercon licensee signed in June.",
        }
    )
    assert resolved.status == "resolved"

    with pytest.raises(ValidationError):
        open_risk.model_copy(update={"status": "resolved"}).model_validate(
            open_risk.model_copy(update={"status": "resolved"}).model_dump()
        )



def test_render_smoke() -> None:
    a = Allocation.load(REPO / "portfolio" / "allocation.yml")
    assert "sankey-beta" in render_capital_flow_sankey(a)

    r = Risk(
        id="R-2026-04-001",
        title="Test",
        ticker="HALO",
        severity="high",
        surfaced_in="manual",
        surfaced_on=date(2026, 4, 26),
        description="d",
        monitor_for="m",
    )
    assert "R-2026-04-001" in render_risk_issue(r)
    assert "Open (1)" in render_risks_index([r])

    wr = WeeklyReview(
        iso_week="2026-W17",
        generated_on=date(2026, 4, 26),
        per_position={
            "VOO": PositionUpdate(
                ticker="VOO",
                news_bullets=["Index up 1.8% on ceasefire ([cite](http://x))"],
                valuation_line="Fwd P/E ~21x ([cite](http://y))",
                thesis_status="still-holds",
                thesis_status_note="Range intact.",
            )
        },
        catalysts_30d=[
            Catalyst(when=date(2026, 5, 5), ticker="ETN", event="Q1 earnings")
        ],
        risks_surfaced=[r.id],
    )
    out = render_weekly_review(wr, {r.id: r})
    assert "Weekly review 2026-W17" in out

    tr = ThesisReview(
        ticker="HALO",
        month="2026-04",
        verdict="still-holds",
        verdict_note="Vertex deal validates the platform.",
        action="no change",
    )
    assert "HALO 2026-04" in render_thesis_review(tr)

    e = EarningsEvent(
        ticker="MKL",
        quarter="1Q26",
        expected_date=date(2026, 4, 29),
        timing="post-close",
        recap=EarningsRecap(
            revenue="Q1 26 revenue $X.XB +Y% YoY",
            eps="EPS $Z.ZZ adj",
            guidance="reiterated",
            sources=["http://primary"],
        ),
    )
    out = render_earnings_event(e)
    assert "Earnings: MKL 1Q26" in out
    assert "Recap" in out


def test_watchlist_entry_buckets_passed() -> None:
    entry = WatchlistEntry(
        ticker="MSFT",
        name="Microsoft",
        sector="Technology",
        added_on=date(2026, 5, 10),
        thesis_note="Dominant cloud + AI platform.",
        screen_results=[
            ScreenResult(bucket="cash", passed=True, note="FCF yield 2.5%"),
            ScreenResult(bucket="finance", passed=True, note="D/E 0.4"),
            ScreenResult(bucket="stability", passed=False, note="CAGR check pending"),
            ScreenResult(bucket="profitability", passed=True, note="ROIC 28%"),
        ],
    )
    assert "cash" in entry.buckets_passed
    assert "stability" not in entry.buckets_passed
    assert not entry.all_buckets_passed


def test_watchlist_entry_all_pass() -> None:
    entry = WatchlistEntry(
        ticker="MSFT",
        name="Microsoft",
        sector="Technology",
        added_on=date(2026, 5, 10),
        thesis_note="Dominant cloud + AI platform.",
        screen_results=[
            ScreenResult(bucket="cash", passed=True),
            ScreenResult(bucket="finance", passed=True),
            ScreenResult(bucket="stability", passed=True),
            ScreenResult(bucket="profitability", passed=True),
        ],
    )
    assert entry.all_buckets_passed


def test_watchlist_loads_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "watchlist.yml"
    p.write_text("watchlist: []\n")
    w = Watchlist.load(p)
    assert w.watchlist == []
    assert w.ready_candidates() == []


def test_render_watchlist_issue() -> None:
    entry = WatchlistEntry(
        ticker="IDXX",
        name="IDEXX Laboratories",
        sector="Healthcare",
        added_on=date(2026, 5, 10),
        conviction="high",
        thesis_note="Veterinary diagnostics monopoly.",
    )
    out = render_watchlist_issue(entry)
    assert "IDXX" in out
    assert "IDEXX Laboratories" in out
    assert "high" in out


def test_scenario_active_and_triggered() -> None:
    s = Scenario(
        id="S-2026-05-001",
        title="Close P if no AI data infra evidence by 12 months",
        ticker="P",
        trigger_type="time-gate",
        trigger_description="12-month mark reached with no AI data infra evidence.",
        action_description="Halt DCA into P; redistribute $8/day.",
    )
    assert s.status == "active"
    assert s.triggered_on is None

    triggered = s.model_copy(
        update={"status": "triggered", "triggered_on": date(2027, 5, 3)}
    )
    assert triggered.status == "triggered"

    with pytest.raises(ValidationError):
        s.model_copy(update={"status": "triggered"}).model_validate(
            s.model_copy(update={"status": "triggered"}).model_dump()
        )


def test_scenario_resolved_requires_note() -> None:
    s = Scenario(
        id="S-2026-05-001",
        title="Test",
        trigger_type="metric",
        trigger_description="FCF yield drops below 3%.",
        action_description="Re-check thesis.",
    )
    with pytest.raises(ValidationError):
        s.model_copy(
            update={
                "status": "resolved",
                "triggered_on": date(2027, 1, 1),
            }
        ).model_validate(
            s.model_copy(
                update={
                    "status": "resolved",
                    "triggered_on": date(2027, 1, 1),
                }
            ).model_dump()
        )


def test_scenario_roundtrip_markdown(tmp_path: Path) -> None:
    s = Scenario(
        id="S-2026-05-001",
        title="HALO royalty concentration",
        ticker="HALO",
        trigger_type="thesis-verdict",
        trigger_description="Thesis review returns 'no' for HALO.",
        action_description="Begin close process for HALO.",
        context="HALO is highest-conviction at 18%; a 'no' verdict warrants immediate action.",
    )
    p = tmp_path / "S-2026-05-001.md"
    p.write_text(s.to_markdown())
    loaded = Scenario.from_markdown(p)
    assert loaded.id == s.id
    assert loaded.trigger_type == s.trigger_type
    assert "Thesis review returns" in loaded.trigger_description


def test_render_scenario_issue() -> None:
    s = Scenario(
        id="S-2026-05-002",
        title="Raise DCA to $150 when portfolio hits $50k",
        trigger_type="dca-shift",
        trigger_description="Deployed capital crosses $50,000.",
        action_description="Update allocation.yml: total_per_day_usd: 150.",
    )
    out = render_scenario_issue(s)
    assert "S-2026-05-002" in out
    assert "dca-shift" in out


def test_horizon_plan_loads_real_file() -> None:
    p = HorizonPlan.load(REPO / "portfolio" / "horizon_plan.yml")
    assert len(p.phases) == 3
    assert p.phases[0].phase == 1
    assert p.current_phase.phase >= 1


def test_horizon_phase_validates_dates() -> None:
    with pytest.raises(ValidationError):
        HorizonPhase(
            phase=1,
            name="Bad",
            start=date(2027, 1, 1),
            end=date(2026, 1, 1),  # end before start
            objective="x",
        )


def test_decision_gate_answered_requires_note() -> None:
    with pytest.raises(ValidationError):
        DecisionGate(question="Is the thesis intact?", answered=True)
    g = DecisionGate(
        question="Is the thesis intact?",
        answered=True,
        answer_note="Yes, all positions hold per Phase 1 review.",
    )
    assert g.is_answered if hasattr(g, "is_answered") else g.answered


def test_render_horizon_review() -> None:
    plan = HorizonPlan.load(REPO / "portfolio" / "horizon_plan.yml")
    out = render_horizon_review(plan)
    assert "Phase" in out
    assert "Accumulate" in out or "Evaluate" in out or "Compound" in out


def test_score_candidate_all_pass() -> None:
    metrics = {
        "fcf_yield_pct": 5.0,
        "net_cash_ratio": 0.1,
        "debt_to_equity": 0.5,
        "interest_coverage": 15.0,
        "current_ratio": 2.0,
        "revenue_cagr_3y_pct": 12.0,
        "earnings_beat_rate_pct": 75.0,
        "gross_margin_pct": 65.0,
        "roic_pct": 20.0,
        "roe_pct": 25.0,
    }
    results = score_candidate(metrics)
    assert len(results) == 4
    assert all(r.passed for r in results)


def test_score_candidate_fail_on_missing_data() -> None:
    metrics: dict = {}  # no data at all
    results = score_candidate(metrics)
    assert not any(r.passed for r in results)
    for r in results:
        assert r.note is not None
        assert "N/A" in (r.note or "")


def test_score_candidate_partial_fail() -> None:
    metrics = {
        "fcf_yield_pct": 1.0,  # below 3% threshold → cash bucket fails
        "net_cash_ratio": 0.2,
        "debt_to_equity": 0.3,
        "interest_coverage": 20.0,
        "current_ratio": 2.5,
        "revenue_cagr_3y_pct": 15.0,
        "earnings_beat_rate_pct": 80.0,
        "gross_margin_pct": 70.0,
        "roic_pct": 22.0,
        "roe_pct": 30.0,
    }
    results = score_candidate(metrics)
    by_bucket = {r.bucket: r for r in results}
    assert not by_bucket["cash"].passed
    assert by_bucket["finance"].passed
    assert by_bucket["stability"].passed
    assert by_bucket["profitability"].passed


def test_metric_keys_complete() -> None:
    keys = metric_keys()
    assert "fcf_yield_pct" in keys
    assert "roic_pct" in keys
    assert len(keys) == 10
