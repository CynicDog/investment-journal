#!/usr/bin/env python3
"""Fetch financial metrics from Alpha Vantage and run the quality screen for one ticker.

Calls 5 AV endpoints (OVERVIEW, BALANCE_SHEET, INCOME_STATEMENT, CASH_FLOW, EARNINGS),
computes all 10 metric keys expected by score_candidate(), and prints a JSON result
ready to be written back into portfolio/watchlist.yml.

Uses ALPHA_VANTAGE_API_KEY_2 — a dedicated key to avoid rate-limit conflicts.

AV free-tier limits: 25 requests/day, 500/month, ~5 req/min.
This script uses 5 calls per ticker; a 12-second sleep enforces the per-minute cap.

Usage:
    uv run python scripts/screen_candidate.py --ticker MSFT

Stdout (JSON, one line):
    {
      "ticker": "MSFT",
      "fetched_on": "2026-05-03",
      "metrics": {"fcf_yield_pct": 2.3, "net_cash_ratio": 0.08, ...},
      "screen_results": [{"bucket": "cash", "passed": true, "note": "..."}, ...]
    }

Errors are written to stderr. On fatal error the process exits non-zero with no stdout.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from investment_journal.models.screener import score_candidate  # noqa: E402

_NONE = {"None", "none", "N/A", "n/a", "", "-"}


def _f(raw: dict, key: str) -> Optional[float]:
    v = raw.get(key)
    if v is None or str(v).strip() in _NONE:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


class _AV:
    BASE = "https://www.alphavantage.co/query"
    _last_call: float = 0.0
    _MIN_GAP = 12.5  # seconds — stays under 5 req/min on free tier

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def get(self, function: str, symbol: str) -> dict:
        gap = time.monotonic() - self.__class__._last_call
        if gap < self._MIN_GAP:
            time.sleep(self._MIN_GAP - gap)
        params = {"function": function, "symbol": symbol, "apikey": self.api_key}
        url = f"{self.BASE}?{urllib.parse.urlencode(params)}"
        sys.stderr.write(f"AV → {function} {symbol}\n")
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read())
        self.__class__._last_call = time.monotonic()
        note = data.get("Note") or data.get("Information")
        if note:
            raise RuntimeError(f"AV returned: {note}")
        return data


def fetch_metrics(ticker: str, api_key: str) -> dict[str, Optional[float]]:
    av = _AV(api_key)

    # 1. OVERVIEW — market cap
    ov = av.get("OVERVIEW", ticker)
    market_cap = _f(ov, "MarketCapitalization")

    # 2. BALANCE_SHEET — most recent annual + prior year for avg equity
    bs_raw = av.get("BALANCE_SHEET", ticker)
    bs_list = bs_raw.get("annualReports", [])
    if not bs_list:
        raise RuntimeError(f"No balance sheet data for {ticker}")
    bs = bs_list[0]
    bs_prev = bs_list[1] if len(bs_list) > 1 else {}

    total_assets = _f(bs, "totalAssets")
    cash = _f(bs, "cashAndShortTermInvestments")
    total_debt = _f(bs, "shortLongTermDebtTotal")
    current_assets = _f(bs, "totalCurrentAssets")
    current_liabs = _f(bs, "totalCurrentLiabilities")
    equity = _f(bs, "totalShareholderEquity")
    equity_prev = _f(bs_prev, "totalShareholderEquity")

    # 3. INCOME_STATEMENT — most recent annual; 4th report for 3yr revenue CAGR
    is_raw = av.get("INCOME_STATEMENT", ticker)
    is_list = is_raw.get("annualReports", [])
    if not is_list:
        raise RuntimeError(f"No income statement data for {ticker}")
    is0 = is_list[0]

    revenue = _f(is0, "totalRevenue")
    gross_profit = _f(is0, "grossProfit")
    ebit = _f(is0, "ebit")
    interest_expense = _f(is0, "interestExpense")
    net_income = _f(is0, "netIncome")
    income_before_tax = _f(is0, "incomeBeforeTax")
    tax_expense = _f(is0, "incomeTaxExpense")
    revenue_3yr_ago = _f(is_list[3], "totalRevenue") if len(is_list) >= 4 else None

    # 4. CASH_FLOW — operating CF + capex for FCF
    cf_raw = av.get("CASH_FLOW", ticker)
    cf_list = cf_raw.get("annualReports", [])
    if not cf_list:
        raise RuntimeError(f"No cash flow data for {ticker}")
    cf = cf_list[0]
    ocf = _f(cf, "operatingCashflow")
    capex = _f(cf, "capitalExpenditures")

    # 5. EARNINGS — EPS beat rate over last 8 reported quarters
    earn_raw = av.get("EARNINGS", ticker)
    quarterly = earn_raw.get("quarterlyEarnings", [])[:8]
    eligible = [
        q
        for q in quarterly
        if _f(q, "reportedEPS") is not None and _f(q, "estimatedEPS") is not None
    ]
    beats = sum(
        1
        for q in eligible
        if (_f(q, "reportedEPS") or 0) > (_f(q, "estimatedEPS") or 0)
    )

    # ── Derive metrics ────────────────────────────────────────────────────────

    # FCF yield %: FCF / market cap × 100
    # capex is reported as negative outflow in AV → FCF = OCF + capex (adding the negative)
    fcf_yield_pct: Optional[float] = None
    if ocf is not None and capex is not None and market_cap and market_cap > 0:
        fcf = ocf - abs(capex)
        fcf_yield_pct = (fcf / market_cap) * 100

    # Net cash / total assets: (cash − total debt) / total assets
    net_cash_ratio: Optional[float] = None
    if (
        cash is not None
        and total_debt is not None
        and total_assets
        and total_assets > 0
    ):
        net_cash_ratio = (cash - total_debt) / total_assets

    # Debt / equity
    debt_to_equity: Optional[float] = None
    if total_debt is not None and equity and equity > 0:
        debt_to_equity = total_debt / equity

    # Interest coverage: EBIT / |interest expense|
    interest_coverage: Optional[float] = None
    if ebit is not None and interest_expense and abs(interest_expense) > 0:
        interest_coverage = ebit / abs(interest_expense)

    # Current ratio
    current_ratio: Optional[float] = None
    if current_assets is not None and current_liabs and current_liabs > 0:
        current_ratio = current_assets / current_liabs

    # Revenue CAGR 3yr %
    revenue_cagr_3y_pct: Optional[float] = None
    if revenue and revenue_3yr_ago and revenue_3yr_ago > 0:
        revenue_cagr_3y_pct = (math.pow(revenue / revenue_3yr_ago, 1 / 3) - 1) * 100

    # EPS beat rate %
    earnings_beat_rate_pct: Optional[float] = (
        (beats / len(eligible)) * 100 if eligible else None
    )

    # Gross margin %
    gross_margin_pct: Optional[float] = None
    if gross_profit is not None and revenue and revenue > 0:
        gross_margin_pct = (gross_profit / revenue) * 100

    # ROIC %: NOPAT / (equity + total debt)
    # NOPAT = EBIT × (1 − effective_tax_rate); tax rate clamped 0–40%
    roic_pct: Optional[float] = None
    if (
        ebit is not None
        and income_before_tax is not None
        and tax_expense is not None
        and income_before_tax > 0
        and equity is not None
        and total_debt is not None
        and (equity + total_debt) > 0
    ):
        tax_rate = max(0.0, min(0.40, tax_expense / income_before_tax))
        nopat = ebit * (1 - tax_rate)
        roic_pct = (nopat / (equity + total_debt)) * 100

    # ROE %: net income / average equity
    roe_pct: Optional[float] = None
    if net_income is not None:
        avg_eq = (
            (equity + equity_prev) / 2
            if equity is not None and equity_prev is not None
            else equity
        )
        if avg_eq and avg_eq > 0:
            roe_pct = (net_income / avg_eq) * 100

    return {
        "fcf_yield_pct": fcf_yield_pct,
        "net_cash_ratio": net_cash_ratio,
        "debt_to_equity": debt_to_equity,
        "interest_coverage": interest_coverage,
        "current_ratio": current_ratio,
        "revenue_cagr_3y_pct": revenue_cagr_3y_pct,
        "earnings_beat_rate_pct": earnings_beat_rate_pct,
        "gross_margin_pct": gross_margin_pct,
        "roic_pct": roic_pct,
        "roe_pct": roe_pct,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ticker", required=True, help="Ticker symbol (e.g. MSFT)")
    ap.add_argument(
        "--api-key",
        default=os.environ.get("ALPHA_VANTAGE_API_KEY_2"),
        dest="api_key",
        help="Alpha Vantage API key. Defaults to $ALPHA_VANTAGE_API_KEY_2.",
    )
    args = ap.parse_args()

    if not args.api_key:
        sys.exit(
            "Missing API key. Set ALPHA_VANTAGE_API_KEY_2 env var or pass --api-key."
        )

    try:
        metrics = fetch_metrics(args.ticker.upper(), args.api_key)
    except Exception as exc:
        sys.stderr.write(f"fetch error for {args.ticker}: {exc}\n")
        return 1

    results = score_candidate(metrics)
    print(
        json.dumps(
            {
                "ticker": args.ticker.upper(),
                "fetched_on": date.today().isoformat(),
                "metrics": metrics,
                "screen_results": [
                    {"bucket": r.bucket, "passed": r.passed, "note": r.note}
                    for r in results
                ],
            },
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
