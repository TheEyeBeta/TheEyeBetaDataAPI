"""Ranking engine for The Eye Beta websearch service.

Scores and ranks tickers using a composite of five factors:

  Factor       Weight
  ----------   ------
  Momentum     40 %
  Trend        25 %
  Quality      15 %
  Volume       10 %
  ADX          10 %

ADX score restored 2026-04-15 — upstream Wilder smoothing fix
confirmed, avg ADX = 43.85, zero tickers pinned at 100.

Each factor sub-score is normalised to [0, 100] before weighting.
Non-bullish tickers receive a neutral ADX score of 50.0 so that a
weak/absent trend does not artificially deflate the composite; only
confirmed bullish structures feed the live ADX percentile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TickerMetrics:
    """Raw market metrics for a single ticker."""

    ticker: str
    # Momentum inputs
    roc_20: float = 0.0          # 20-day rate-of-change (%)
    rsi_14: float = 50.0         # 14-day RSI
    macd_hist: float = 0.0       # MACD histogram value
    # Trend inputs
    ema_spread_pct: float = 0.0  # (price - EMA200) / EMA200 * 100
    adx_14: float = 0.0          # 14-period Wilder-smoothed ADX
    is_bullish: bool = False      # True when price > EMA50 > EMA200
    # Quality inputs
    earnings_surprise: float = 0.0  # Most-recent EPS beat (%)
    debt_equity: float = 1.0        # D/E ratio (lower = better)
    roe: float = 0.0                # Return on equity (%)
    # Volume inputs
    rvol: float = 1.0            # Relative volume vs 20-day average
    obv_slope: float = 0.0       # OBV linear-regression slope (normalised)


@dataclass
class RankedTicker:
    """Composite score and component breakdown for a ticker."""

    ticker: str
    composite: float = 0.0
    m_score: float = 0.0
    t_score: float = 0.0
    q_score: float = 0.0
    v_score: float = 0.0
    a_score: float = 0.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _momentum_score(m: TickerMetrics) -> float:
    """Momentum sub-score [0, 100]."""
    # RSI component: centre at 50, scale to 0-100
    rsi_c = _clamp(m.rsi_14)

    # ROC component: map [-20, +20] % to [0, 100]
    roc_c = _clamp(50.0 + m.roc_20 * 2.5)

    # MACD histogram: soft-clip via tanh, then map to [0, 100]
    import math
    macd_c = _clamp(50.0 + math.tanh(m.macd_hist / 0.5) * 50.0)

    return round((rsi_c * 0.4 + roc_c * 0.35 + macd_c * 0.25), 4)


def _trend_score(m: TickerMetrics) -> float:
    """Trend sub-score [0, 100].

    Measures the strength and direction of the prevailing trend via the
    EMA200 spread.  ADX contribution is handled separately in _adx_score
    and blended at the composite level.
    """
    # EMA spread: map [-10 %, +10 %] to [0, 100]
    spread_c = _clamp(50.0 + m.ema_spread_pct * 5.0)

    # Trend direction bonus: being above both MAs lifts the score
    direction_bonus = 10.0 if m.is_bullish else 0.0

    return round(_clamp(spread_c + direction_bonus), 4)


def _quality_score(m: TickerMetrics) -> float:
    """Quality (fundamental) sub-score [0, 100]."""
    # Earnings surprise: map [-10 %, +10 %] to [0, 100]
    eps_c = _clamp(50.0 + m.earnings_surprise * 5.0)

    # D/E: low is better — map [0, 4] inversely to [100, 0]
    de_c = _clamp(100.0 - m.debt_equity * 25.0)

    # ROE: map [0 %, 40 %] to [0, 100]
    roe_c = _clamp(m.roe * 2.5)

    return round((eps_c * 0.35 + de_c * 0.30 + roe_c * 0.35), 4)


def _volume_score(m: TickerMetrics) -> float:
    """Volume sub-score [0, 100]."""
    # RVOL: map [0×, 4×] to [0, 100]
    rvol_c = _clamp(m.rvol * 25.0)

    # OBV slope: map [-1, +1] (pre-normalised) to [0, 100]
    obv_c = _clamp(50.0 + m.obv_slope * 50.0)

    return round((rvol_c * 0.5 + obv_c * 0.5), 4)


def _adx_score(m: TickerMetrics) -> float:
    """ADX sub-score [0, 100].

    Only bullish tickers receive a live score derived from the actual ADX
    reading.  Non-bullish tickers fall back to the neutral value of 50.0
    so that a weak or absent trend does not artificially penalise them in
    the composite.

    Neutral fallback: 50.0  (NOT 0.0 — confirmed fix, must not regress)
    """
    if not m.is_bullish:
        return 50.0  # neutral — non-bullish tickers are not penalised

    # ADX ∈ [0, 100]; map linearly, capped
    return round(_clamp(m.adx_14), 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_ticker(m: TickerMetrics) -> RankedTicker:
    """Compute component and composite scores for *m*."""
    m_score = _momentum_score(m)
    t_score = _trend_score(m)
    q_score = _quality_score(m)
    v_score = _volume_score(m)
    a_score = _adx_score(m)

    # Composite weights: momentum 40%, trend 25%,
    # quality 15%, volume 10%, ADX 10%
    # ADX restored 2026-04-15 — upstream Wilder
    # smoothing fix confirmed, avg ADX = 43.85,
    # zero tickers pinned at 100.
    composite = round(
        0.40 * m_score
        + 0.25 * t_score
        + 0.15 * q_score
        + 0.10 * v_score
        + 0.10 * a_score,
        2,
    )

    return RankedTicker(
        ticker=m.ticker,
        composite=composite,
        m_score=m_score,
        t_score=t_score,
        q_score=q_score,
        v_score=v_score,
        a_score=a_score,
    )


def rank_tickers(metrics: Sequence[TickerMetrics]) -> list[RankedTicker]:
    """Score and rank a universe of tickers, highest composite first."""
    ranked = [score_ticker(m) for m in metrics]
    ranked.sort(key=lambda r: r.composite, reverse=True)
    return ranked
