-- ASSUMED SHAPES — NOT VERIFIED AGAINST TheEyeBetaProd.
--
-- Objects TheEyeBetaDataAPI reads that exist only on the production host:
-- no TheEyeBetaProd migration creates them (contracts/prod/PROD_SHA). Each
-- table below lists exactly the columns DataAPI's SQL reads, so the contract
-- gate can execute those routes. Types are DataAPI's expectations, not facts.
-- This file is DataAPI's requirement list for Prod: once Prod adopts an object
-- into a migration, delete it here, move it to objects.txt and regenerate.
-- Tracked in docs/TECH_DEBT.md (DEBT-04). Must stay in sync with
-- host_only_tables.txt (checked by tests/contract).

-- Host table has 72 columns (Prod docs/db-engineer/references/theeyebeta-schema.md);
-- Prod's latest_snapshot_worker model has 40 and no eps.
ALTER TABLE theeyebeta.latest_snapshots ADD COLUMN eps numeric;

CREATE TABLE theeyebeta.fund_income_q (
    instrument_id bigint NOT NULL, period_end date, fiscal_year integer, fiscal_quarter integer,
    revenue numeric, gross_profit numeric, ebit numeric, ebitda numeric, interest_expense numeric,
    net_income numeric, eps_basic numeric, eps_diluted numeric
);
CREATE TABLE theeyebeta.fund_balance_q (
    instrument_id bigint NOT NULL, period_end date, fiscal_year integer, fiscal_quarter integer,
    total_assets numeric, total_liabilities numeric, total_equity numeric, total_debt numeric,
    cash_and_equivalents numeric, shares_outstanding numeric
);
CREATE TABLE theeyebeta.fund_cashflow_q (
    instrument_id bigint NOT NULL, period_end date, fiscal_year integer, fiscal_quarter integer,
    ocf numeric, capex numeric, fcf numeric, working_cap_change numeric, stock_based_comp numeric
);
CREATE TABLE theeyebeta.ind_risk_daily (
    instrument_id bigint NOT NULL, date date NOT NULL, atr_14 numeric, hist_vol_20d numeric,
    hist_vol_60d numeric, beta_sp500_60d numeric, worst_drop_1d numeric, worst_drop_5d numeric,
    worst_drop_10d numeric, max_drawdown_1y numeric, max_drawdown_2y numeric, sharpe_60d numeric,
    sortino_60d numeric, calmar_1y numeric
);
CREATE TABLE theeyebeta.ind_valuation_daily (
    instrument_id bigint NOT NULL, date date NOT NULL, market_cap numeric, enterprise_value numeric,
    pe_ttm numeric, forward_pe numeric, ps_ttm numeric, pb numeric, ev_ebitda numeric, ev_ebit numeric,
    ev_fcf numeric, earnings_yield numeric, fcf_yield numeric, pct_chg_1w numeric, pct_chg_3m numeric,
    pct_chg_6m numeric, pct_chg_9m numeric, pct_chg_ytd numeric, pct_chg_1y numeric
);
CREATE TABLE theeyebeta.returns_snapshot_daily (
    instrument_id bigint NOT NULL, date date NOT NULL, ret_1w numeric, ret_1m numeric, ret_3m numeric,
    ret_6m numeric, ret_9m numeric, ret_ytd numeric, ret_1y numeric, price_field text,
    computed_at timestamptz
);
CREATE TABLE theeyebeta.ticker_news (
    news_id bigint, instrument_id bigint NOT NULL, source text, title text, url text,
    published_at timestamptz, summary text, sentiment text, sentiment_score numeric
);
CREATE TABLE theeyebeta.provider_sync_runs (
    sync_name text, started_at timestamptz, completed_at timestamptz, status text, error_message text
);
CREATE TABLE theeyebeta.price_ticks (
    tick_id bigint, instrument_id bigint NOT NULL, ts timestamptz, price numeric, open numeric,
    high numeric, low numeric, close numeric, volume numeric, source text
);
CREATE TABLE theeyebeta.trask_audit_events_archive (
    event_id uuid, event_type text, event_category text, source_type text, source_id text,
    target_type text, target_id text, severity text, payload jsonb, created_at timestamptz
);
