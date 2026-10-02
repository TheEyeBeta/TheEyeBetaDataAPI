-- Minimal, deterministic rows for the Prod schema contract tests.
-- Runs as the database owner after contracts/prod/theeyebeta_schema.sql.
-- Column names and NOT NULL/CHECK constraints come from TheEyeBetaProd's
-- migrations; if Prod changes them this file fails loudly at setup.

INSERT INTO theeyebeta.exchanges (id, code, name, country_iso2, timezone, currency_iso)
VALUES (1, 'XNAS', 'Nasdaq', 'US', 'America/New_York', 'USD');

INSERT INTO theeyebeta.instruments (id, symbol, exchange_id, asset_class, sector, industry, active, metadata)
VALUES
  (1, 'AAPL', 1, 'equity', 'Technology', 'Consumer Electronics', true, '{"name": "Apple Inc."}'::jsonb),
  (2, 'MSFT', 1, 'equity', 'Technology', 'Software', true, '{"name": "Microsoft Corp."}'::jsonb);

INSERT INTO theeyebeta.public_ticker_map (instrument_id, public_ticker_id) VALUES (1, 101), (2, 102);

INSERT INTO theeyebeta.prices_daily (instrument_id, ts, open, high, low, close, adj_close, volume, source)
SELECT i, d::timestamptz, 100 + n, 102 + n, 99 + n, 101 + n, 101 + n, 1000000 + n, 'contract'
FROM (VALUES (1), (2)) AS inst(i),
     LATERAL (SELECT d, row_number() OVER (ORDER BY d) AS n
              FROM generate_series('2026-09-21'::date, '2026-09-25'::date, interval '1 day') AS d) days;

INSERT INTO theeyebeta.ind_technical_daily
  (instrument_id, date, ticker_id, sma_10, sma_50, sma_200, rsi_14, macd, macd_signal, macd_hist)
VALUES (1, '2026-09-25', 101, 104, 102, 98, 56.5, 1.2, 1.0, 0.2),
       (2, '2026-09-25', 102, 420, 410, 390, 61.0, 2.1, 1.8, 0.3);

INSERT INTO theeyebeta.market_cap_daily (symbol, instrument_id, as_of_date, market_cap, close_price, shares_outstanding, source)
VALUES ('AAPL', 1, '2026-09-25', 3400000000000, 106, 15000000000, 'contract'),
       ('MSFT', 2, '2026-09-25', 3100000000000, 106, 7400000000, 'contract');

INSERT INTO theeyebeta.market_news (provider, url, headline, summary, source, category, related, published_at, content_hash)
VALUES ('finnhub', 'https://example.com/a', 'Apple ships new phone', 'Summary', 'Example Wire', 'company', 'AAPL',
        '2026-09-25 14:00:00+00', 'hash-a'),
       ('finnhub', 'https://example.com/m', 'Markets close higher', 'Summary', 'Example Wire', 'general', '',
        '2026-09-25 21:00:00+00', 'hash-m');

INSERT INTO theeyebeta.fundamentals (instrument_id, period_end, period_type, revenue, net_income, eps, pe_ratio, source)
VALUES (1, '2026-06-30', 'Q', 94000000000, 23000000000, 1.45, 29.5, 'contract');

INSERT INTO theeyebeta.fundamentals_company (ticker_id, instrument_id, sector, industry, market_cap, pe_ratio, currency, source)
VALUES (101, 1, 'Technology', 'Consumer Electronics', 3400000000000, 29.5, 'USD', 'contract');

INSERT INTO theeyebeta.corporate_actions (instrument_id, ex_date, action_type, ratio_num, ratio_den, cash_amount, currency_iso)
VALUES (1, '2026-08-10', 'dividend', NULL, NULL, 0.26, 'USD');

INSERT INTO theeyebeta.macro_indicators (series_code, ts, value, source)
VALUES ('DGS10', '2026-09-24 00:00:00+00', 4.18, 'FRED'),
       ('DGS10', '2026-09-25 00:00:00+00', 4.21, 'FRED'),
       ('UNRATE', '2026-08-01 00:00:00+00', 4.1, 'FRED');

INSERT INTO theeyebeta.fixed_income_curve_metrics
  (date, country, currency, y_2y, y_10y, y_30y, spread_10y_2y, curve_regime, rate_regime, credit_regime,
   bond_environment_score, bond_environment_label, source)
VALUES ('2026-09-25', 'US', 'USD', 3.62, 4.21, 4.55, 0.59, 'normal', 'stable', 'tight', 62, 'supportive', 'contract');

INSERT INTO theeyebeta.fixed_income_signals
  (date, country, signal_name, signal_value, signal_strength, signal_direction, interpretation)
VALUES ('2026-09-25', 'US', 'curve_steepening', 0.12, 'moderate', 'risk_on', 'Curve steepened.');

INSERT INTO theeyebeta.sector_daily (sector, as_of_date, n_instruments, avg_return_1d, rotation_rank, top_contributors)
VALUES ('Technology', '2026-09-25', 2, 0.004, 1, '[]'::jsonb);

INSERT INTO theeyebeta.trading_calendar (calendar_date, is_trading_day, market_name, holiday_name)
VALUES ('2026-09-25', true, 'NYSE', NULL), ('2026-11-26', false, 'NYSE', 'Thanksgiving');

INSERT INTO theeyebeta.audit_cap_events (trade_date, symbol, instrument_id, event_type, market_cap, action_required)
VALUES ('2026-09-24', 'MSFT', 2, 'CROSSED_UP', 3100000000000, 'add');

INSERT INTO theeyebeta.worker_heartbeats (worker_id, worker_type, status, last_heartbeat)
VALUES ('price-ingest-1', 'ingest', 'running', '2026-09-25 21:00:00+00');

-- Production's worker-maintained table (Prod workers/latest_snapshot_worker.py columns).
INSERT INTO theeyebeta.latest_snapshots
  (instrument_id, ticker_id, last_price, last_price_ts, price_change_pct, price_change_abs, prev_close,
   volume, sma_10, sma_50, sma_200, rsi_14, macd, macd_signal, macd_hist, pe_ratio, market_cap,
   latest_signal, signal_strategy, signal_confidence, signal_ts, updated_at)
VALUES
  (1, 101, 106, '2026-09-25 20:00:00+00', 0.95, 1, 105, 1000005, 104, 102, 98, 56.5, 1.2, 1.0, 0.2, 29.5,
   3400000000000, 'BUY', 'momentum_rsi', 0.71, '2026-09-25 20:00:00+00', '2026-09-25 21:00:00+00'),
  (2, 102, 106, '2026-09-25 20:00:00+00', 0.95, 1, 105, 1000005, 420, 410, 390, 61.0, 2.1, 1.8, 0.3, 35.1,
   3100000000000, NULL, NULL, NULL, NULL, '2026-09-25 21:00:00+00');

-- Host-only objects (contracts/prod/host_only_assumed.sql shapes).
UPDATE theeyebeta.latest_snapshots SET eps = 6.42 WHERE instrument_id = 1;
INSERT INTO theeyebeta.fund_income_q (instrument_id, period_end, fiscal_year, fiscal_quarter, revenue, net_income, eps_basic, eps_diluted)
VALUES (1, '2026-06-30', 2026, 3, 94000000000, 23000000000, 1.46, 1.45);
INSERT INTO theeyebeta.fund_balance_q (instrument_id, period_end, fiscal_year, fiscal_quarter, total_assets, total_equity)
VALUES (1, '2026-06-30', 2026, 3, 350000000000, 66000000000);
INSERT INTO theeyebeta.fund_cashflow_q (instrument_id, period_end, fiscal_year, fiscal_quarter, ocf, capex, fcf)
VALUES (1, '2026-06-30', 2026, 3, 28000000000, -2500000000, 25500000000);
INSERT INTO theeyebeta.ind_risk_daily (instrument_id, date, atr_14, hist_vol_20d, beta_sp500_60d) VALUES (1, '2026-09-25', 2.1, 0.22, 1.1);
INSERT INTO theeyebeta.ind_valuation_daily (instrument_id, date, market_cap, pe_ttm, pct_chg_1w) VALUES (1, '2026-09-25', 3400000000000, 29.5, 0.012);
INSERT INTO theeyebeta.returns_snapshot_daily (instrument_id, date, ret_1w, ret_1m, price_field) VALUES (1, '2026-09-25', 0.012, 0.03, 'adj_close');
INSERT INTO theeyebeta.ticker_news (news_id, instrument_id, source, title, url, published_at, sentiment, sentiment_score)
VALUES (1, 1, 'Example Wire', 'Apple ships new phone', 'https://example.com/a', '2026-09-25 14:00:00+00', 'positive', 0.6);
INSERT INTO theeyebeta.provider_sync_runs (sync_name, started_at, completed_at, status) VALUES ('prices_daily', '2026-09-25 21:00:00+00', '2026-09-25 21:05:00+00', 'success');
INSERT INTO theeyebeta.price_ticks (tick_id, instrument_id, ts, price, close, volume, source) VALUES (1, 1, '2026-09-25 19:59:00+00', 106, 106, 500, 'contract');
INSERT INTO theeyebeta.trask_audit_events_archive (event_id, event_type, event_category, severity, payload, created_at)
VALUES ('6f1c9a2e-0000-4000-8000-000000000001', 'worker_restart', 'ops', 'info', '{}'::jsonb, '2026-09-25 21:00:00+00');
