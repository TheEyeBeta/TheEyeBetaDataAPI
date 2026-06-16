#!/usr/bin/env python3
"""Report legacy public table coverage in the canonical theeyebeta schema."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


@dataclass(frozen=True)
class TablePair:
    public_table: str
    theeyebeta_table: str


TABLE_PAIRS: tuple[TablePair, ...] = (
    TablePair("tickers", "instruments"),
    TablePair("latest_snapshot", "latest_snapshots"),
    TablePair("price_daily", "prices_daily"),
    TablePair("price_ticks", "price_ticks"),
    TablePair("ind_technical_daily", "ind_technical_daily"),
    TablePair("ind_risk_daily", "ind_risk_daily"),
    TablePair("ind_valuation_daily", "ind_valuation_daily"),
    TablePair("returns_snapshot_daily", "returns_snapshot_daily"),
    TablePair("corporate_actions", "corporate_actions"),
    TablePair("fund_income_q", "fund_income_q"),
    TablePair("fund_balance_q", "fund_balance_q"),
    TablePair("fund_cashflow_q", "fund_cashflow_q"),
    TablePair("fundamentals_company", "fundamentals_company"),
    TablePair("market_news", "market_news"),
    TablePair("news", "ticker_news"),
    TablePair("trading_calendar", "trading_calendar"),
)


def _database_url(cli_value: str | None) -> str:
    value = cli_value or os.getenv("DATABASE_URL")
    if not value:
        raise SystemExit("DATABASE_URL is required")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="SQLAlchemy database URL. Defaults to DATABASE_URL.")
    args = parser.parse_args()

    engine = create_engine(_database_url(args.database_url), pool_pre_ping=True)
    query = text(
        """
        WITH pairs(public_table, theeyebeta_table) AS (
            VALUES
            (:p0, :t0), (:p1, :t1), (:p2, :t2), (:p3, :t3),
            (:p4, :t4), (:p5, :t5), (:p6, :t6), (:p7, :t7),
            (:p8, :t8), (:p9, :t9), (:p10, :t10), (:p11, :t11),
            (:p12, :t12), (:p13, :t13), (:p14, :t14), (:p15, :t15)
        )
        SELECT
            pairs.public_table,
            pairs.theeyebeta_table,
            pt.table_name IS NOT NULL AS public_exists,
            tt.table_name IS NOT NULL AS theeyebeta_exists,
            COALESCE(ps.n_live_tup, 0) AS public_approx_rows,
            COALESCE(ts.n_live_tup, 0) AS theeyebeta_approx_rows
        FROM pairs
        LEFT JOIN information_schema.tables pt
          ON pt.table_schema = 'public'
         AND pt.table_name = pairs.public_table
        LEFT JOIN information_schema.tables tt
          ON tt.table_schema = 'theeyebeta'
         AND tt.table_name = pairs.theeyebeta_table
        LEFT JOIN pg_stat_user_tables ps
          ON ps.schemaname = 'public'
         AND ps.relname = pairs.public_table
        LEFT JOIN pg_stat_user_tables ts
          ON ts.schemaname = 'theeyebeta'
         AND ts.relname = pairs.theeyebeta_table
        ORDER BY pairs.public_table
        """
    )
    params: dict[str, str] = {}
    for idx, pair in enumerate(TABLE_PAIRS):
        params[f"p{idx}"] = pair.public_table
        params[f"t{idx}"] = pair.theeyebeta_table

    try:
        with engine.connect() as conn:
            rows = conn.execute(query, params).mappings().all()
    except SQLAlchemyError as exc:
        print(f"coverage check failed: {exc}", file=sys.stderr)
        return 2

    failures = 0
    print("public_table,theeyebeta_table,public_exists,theeyebeta_exists,public_approx_rows,theeyebeta_approx_rows,status")
    for row in rows:
        status = "ok" if row["theeyebeta_exists"] else "missing_theeyebeta"
        if status != "ok":
            failures += 1
        print(
            ",".join(
                [
                    str(row["public_table"]),
                    str(row["theeyebeta_table"]),
                    str(row["public_exists"]).lower(),
                    str(row["theeyebeta_exists"]).lower(),
                    str(row["public_approx_rows"]),
                    str(row["theeyebeta_approx_rows"]),
                    status,
                ]
            )
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
