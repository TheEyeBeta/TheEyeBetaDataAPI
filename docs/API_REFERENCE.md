# TheEyeBeta DataAPI — API Reference

Base URL: `https://api.theeyebeta.store` (or `http://127.0.0.1:7000` locally)

All versioned endpoints are under `/api/v1/`.

Runtime data endpoints read from the canonical `theeyebeta` schema only. The
legacy `public` schema is deprecated for this API; any missing mirror data is a
data-sync issue, not a runtime fallback path. This API is read-only.

---

## Table of Contents

1. [Authentication](#authentication)
2. [Scopes](#scopes)
3. [Error Format](#error-format)
4. [Health](#health)
5. [Auth — Service Tokens](#auth--service-tokens)
6. [Market Data](#market-data)
7. [Symbols](#symbols)
8. [Tickers](#tickers)
9. [Financials](#financials)
10. [Indicators](#indicators)
11. [Analytics](#analytics)
12. [Signals](#signals)
13. [News](#news)
14. [Reference Data](#reference-data)
15. [Advisor](#advisor)
16. [Portfolio](#portfolio)
17. [Generic Data Tables](#generic-data-tables)
18. [Admin](#admin)

---

## Authentication

All endpoints except `GET /health` and `GET /api/v1/admin/dashboard` require a Bearer token in the `Authorization` header.

```
Authorization: Bearer <token>
```

**Service principals** obtain tokens via the client credentials flow (see [Auth — Service Tokens](#auth--service-tokens)).

**User principals** supply a JWT issued by the configured user auth provider (`USER_JWT_SECRET` or OIDC/JWKS).

### Getting a service token (quick start)

```bash
TOKEN=$(curl -s -X POST "https://api.theeyebeta.store/api/v1/auth/service-token" \
  -u "<CLIENT_ID>:<CLIENT_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"requested_scopes":["market:read","analytics:read"]}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

Then use the token:

```bash
curl -s "https://api.theeyebeta.store/api/v1/market-data/quotes?symbols=AAPL,MSFT" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Scopes

Each endpoint requires one of the following scopes. A token is only granted the scopes you explicitly request (up to what the client is allowed).

| Scope | Access granted |
|---|---|
| `market:read` | Quotes, price history, news, reference data, tickers |
| `symbols:read` | Symbol search |
| `analytics:read` | Analytics snapshots, financials, indicators, fundamentals |
| `signals:read` | Trading signals |
| `advisor:read` | AI advisor chat and context |
| `portfolio:read` | Portfolio state |
| `admin:read` | Admin dashboard, audit events, ETL status, named queries, all table reads |
| `admin:*` | All admin scopes (wildcard) |

---

## Error Format

All errors return a JSON body:

```json
{
  "detail": "Human-readable error message"
}
```

Common HTTP status codes:

| Code | Meaning |
|---|---|
| `400` | Validation error (bad parameters or request body) |
| `401` | Missing or invalid token |
| `403` | Token present but missing required scope |
| `404` | Resource not found |
| `422` | Request body schema violation |
| `500` | Internal server error |

---

## Health

### `GET /health`

Returns API liveness and dependency health. No auth required. The top-level `status` reports whether the API process is serving requests; dependency fields such as `database` expose downstream availability separately.

**Response**

```json
{
  "status": "healthy",
  "database": true
}
```

**Example**

```bash
curl -s https://api.theeyebeta.store/health
```

---

## Auth — Service Tokens

### `POST /api/v1/auth/service-token`

Exchange service client credentials for a scoped Bearer token.

**Authentication:** HTTP Basic — username is `client_id`, password is `client_secret`.

**Request body**

```json
{
  "requested_scopes": ["market:read", "analytics:read"]
}
```

| Field | Type | Description |
|---|---|---|
| `requested_scopes` | `string[]` | List of scopes to request. Must be a subset of the scopes the client is allowed. |

**Response**

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_minutes": 60,
  "scopes": ["market:read", "analytics:read"]
}
```

**Example**

```bash
curl -s -X POST "https://api.theeyebeta.store/api/v1/auth/service-token" \
  -u "my-client-id:my-client-secret" \
  -H "Content-Type: application/json" \
  -d '{"requested_scopes":["market:read","signals:read","portfolio:read"]}'
```

---

## Market Data

### `GET /api/v1/market-data/quotes`

Real-time / latest-available quotes for one or more symbols.

**Scope:** `market:read`

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `symbols` | string | Yes | Comma-separated list of tickers (e.g. `AAPL,MSFT,TSLA`) |

**Response**

```json
{
  "quotes": [
    {
      "ticker": "AAPL",
      "company_name": "Apple Inc.",
      "last_price": 189.42,
      "price_change_pct": 0.82,
      "rsi_14": 61.3,
      "sma_10": 187.1,
      "sma_50": 182.5,
      "sma_200": 175.0,
      "macd": 1.23,
      "macd_signal": 0.98,
      "macd_hist": 0.25,
      "updated_at": "2025-05-03T14:30:00Z"
    }
  ]
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/market-data/quotes?symbols=AAPL,MSFT" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Symbols

### `GET /api/v1/symbols/search`

Search for tickers by name or symbol prefix.

**Scope:** `symbols:read`

**Query parameters**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `q` | string | Yes | — | 1–64 chars | Search query (ticker symbol or company name) |
| `limit` | integer | No | `25` | 1–100 | Max results to return |

**Response**

```json
{
  "results": [
    {
      "ticker": "AAPL",
      "company_name": "Apple Inc."
    }
  ]
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/symbols/search?q=apple&limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

### `GET /api/v1/symbols/resolve`

Resolve one exact, case-insensitive symbol against the security master.

**Scope:** `symbols:read`

The request succeeds only when the normalized symbol identifies exactly one
`theeyebeta.instruments` row. If the same symbol exists on more than one exchange, the endpoint
returns `409 CONFLICT` instead of selecting a venue silently. A missing symbol returns
`404 NOT FOUND`.

**Query parameters**

| Parameter | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `symbol` | string | Yes | 1–64 chars | Exact symbol; surrounding whitespace is ignored and matching is case-insensitive |

**Response**

```json
{
  "instrument_id": 123,
  "name": "Apple Inc.",
  "exchange": "NASDAQ",
  "currency": "USD",
  "isin": null,
  "cusip": null,
  "figi": null,
  "asset_class": "equity",
  "active": true
}
```

`exchange` is the canonical `exchanges.code`; `currency` is its ISO currency code. ISIN, CUSIP,
and FIGI are nullable because the security-master columns are nullable.

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/symbols/resolve?symbol=AAPL" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Tickers

### `GET /api/v1/tickers/{ticker}`

Full detail for a single ticker.

**Scope:** `market:read`

**Path parameters**

| Parameter | Description |
|---|---|
| `ticker` | Ticker symbol (case-insensitive, normalized to uppercase) |

**Response**

```json
{
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "asset_type": "equity",
  "country_code": "US",
  "timezone": "America/New_York",
  "currency_code": "USD",
  "is_active": true,
  "sector_id": 4,
  "industry_id": 21,
  "website": "https://www.apple.com",
  "description": "Apple Inc. designs, manufactures...",
  "founded_year": 1976,
  "employees": 164000,
  "identifiers": [
    { "id_type": "isin", "id_value": "US0378331005" }
  ]
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/tickers/AAPL" \
  -H "Authorization: Bearer $TOKEN"
```

---

### `GET /api/v1/tickers/{ticker}/price-history`

Daily OHLCV price history for a ticker.

**Scope:** `market:read`

**Path parameters**

| Parameter | Description |
|---|---|
| `ticker` | Ticker symbol |

**Query parameters**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `start` | date (`YYYY-MM-DD`) | No | — | — | Start date inclusive |
| `end` | date (`YYYY-MM-DD`) | No | — | — | End date inclusive |
| `limit` | integer | No | `252` | 1–2000 | Max rows (applied after date filter) |

**Response**

```json
{
  "ticker": "AAPL",
  "prices": [
    {
      "date": "2025-05-02",
      "open": 188.10,
      "high": 190.55,
      "low": 187.60,
      "close": 189.42,
      "adj_close": 189.42,
      "volume": 54312000,
      "vwap": 189.01
    }
  ]
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/tickers/AAPL/price-history?start=2025-01-01&limit=90" \
  -H "Authorization: Bearer $TOKEN"
```

---

### `GET /api/v1/tickers/{ticker}/corporate-actions`

Splits and dividends for a ticker.

**Scope:** `market:read`

**Path parameters**

| Parameter | Description |
|---|---|
| `ticker` | Ticker symbol |

**Query parameters**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `limit` | integer | No | `50` | 1–500 | Max records |

**Response**

```json
{
  "ticker": "AAPL",
  "actions": [
    {
      "action_id": 12,
      "action_date": "2020-08-31",
      "action_type": "split",
      "split_ratio": 4.0,
      "dividend_amount": null,
      "notes": "4-for-1 stock split"
    }
  ]
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/tickers/AAPL/corporate-actions" \
  -H "Authorization: Bearer $TOKEN"
```

---

### `GET /api/v1/tickers/{ticker}/fundamentals`

Static company fundamentals snapshot (valuation multiples, share count, dividend info, etc.).

**Scope:** `analytics:read`

**Path parameters**

| Parameter | Description |
|---|---|
| `ticker` | Ticker symbol |

**Response**

```json
{
  "ticker": "AAPL",
  "sector": "Technology",
  "industry": "Consumer Electronics",
  "sub_industry": null,
  "ceo": "Tim Cook",
  "full_time_employees": 164000,
  "headquarters_city": "Cupertino",
  "headquarters_state": "CA",
  "headquarters_country": "US",
  "market_cap": 2940000000000,
  "enterprise_value": 2960000000000,
  "shares_outstanding": 15500000000,
  "float_shares": 15490000000,
  "pe_ratio": 29.4,
  "pe_forward": 27.1,
  "peg_ratio": 2.1,
  "price_to_book": 45.2,
  "price_to_sales": 7.8,
  "ev_to_ebitda": 21.3,
  "ev_to_revenue": 7.9,
  "dividend_rate": 0.96,
  "dividend_yield": 0.0051,
  "ex_dividend_date": "2025-02-07",
  "payout_ratio": 0.145,
  "currency": "USD",
  "source": "fundamentals_feed",
  "last_updated": "2025-05-01T00:00:00Z"
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/tickers/AAPL/fundamentals" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Financials

All financial endpoints return quarterly period data ordered from most recent to oldest.

**Scope for all:** `analytics:read`

**Common query parameter**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `limit` | integer | No | `12` | 1–40 | Number of quarterly periods to return |

---

### `GET /api/v1/financials/{ticker}/income`

Quarterly income statements.

**Response**

```json
{
  "ticker": "AAPL",
  "statements": [
    {
      "period_end": "2024-12-31",
      "fiscal_year": 2024,
      "fiscal_quarter": 4,
      "revenue": 124300000000,
      "gross_profit": 58400000000,
      "ebit": 43900000000,
      "ebitda": 47100000000,
      "interest_expense": 700000000,
      "net_income": 36300000000,
      "eps_basic": 2.42,
      "eps_diluted": 2.40
    }
  ]
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/financials/AAPL/income?limit=8" \
  -H "Authorization: Bearer $TOKEN"
```

---

### `GET /api/v1/financials/{ticker}/balance`

Quarterly balance sheets.

**Response**

```json
{
  "ticker": "AAPL",
  "statements": [
    {
      "period_end": "2024-12-31",
      "fiscal_year": 2024,
      "fiscal_quarter": 4,
      "total_assets": 364980000000,
      "total_liabilities": 308030000000,
      "total_equity": 56950000000,
      "total_debt": 101040000000,
      "cash_and_equivalents": 29940000000,
      "shares_outstanding": 15204137000
    }
  ]
}
```

---

### `GET /api/v1/financials/{ticker}/cashflow`

Quarterly cash flow statements.

**Response**

```json
{
  "ticker": "AAPL",
  "statements": [
    {
      "period_end": "2024-12-31",
      "fiscal_year": 2024,
      "fiscal_quarter": 4,
      "ocf": 40100000000,
      "capex": -2900000000,
      "fcf": 37200000000,
      "working_cap_change": -1200000000,
      "stock_based_comp": 2900000000
    }
  ]
}
```

---

### `GET /api/v1/financials/{ticker}/quality`

Quarterly quality and profitability metrics (ROIC, ROE, WACC, leverage, coverage).

**Response**

```json
{
  "ticker": "AAPL",
  "metrics": [
    {
      "period_end": "2024-12-31",
      "fiscal_year": 2024,
      "fiscal_quarter": 4,
      "nopat": 38200000000,
      "invested_capital": 145000000000,
      "roic": 0.263,
      "roe": 1.54,
      "roa": 0.099,
      "roce": 0.31,
      "wacc": 0.089,
      "cost_of_equity": 0.095,
      "cost_of_debt": 0.031,
      "roic_wacc_spread": 0.174,
      "debt_equity": 1.77,
      "net_debt_ebitda": 0.6,
      "interest_coverage": 62.7,
      "ocf": 40100000000,
      "fcf": 37200000000
    }
  ]
}
```

---

## Indicators

All indicator endpoints return daily time-series data. They share the same date/limit query parameters.

**Scope for all:** `analytics:read`

**Common query parameters**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `start` | date (`YYYY-MM-DD`) | No | — | — | Start date inclusive |
| `end` | date (`YYYY-MM-DD`) | No | — | — | End date inclusive |
| `limit` | integer | No | `252` | 1–2000 | Max rows (applied after date filter) |

---

### `GET /api/v1/indicators/{ticker}/technical`

Daily moving averages, RSI, MACD, rate-of-change, and crossover signals.

**Response**

```json
{
  "ticker": "AAPL",
  "indicators": [
    {
      "date": "2025-05-02",
      "sma_10": 187.1,
      "sma_50": 182.5,
      "sma_200": 175.0,
      "ema_10": 187.8,
      "ema_50": 183.1,
      "ema_200": 175.4,
      "ema_12": 187.5,
      "ema_26": 184.2,
      "rsi_14": 61.3,
      "macd": 1.23,
      "macd_signal": 0.98,
      "macd_hist": 0.25,
      "roc_10": 2.1,
      "roc_20": 4.3,
      "golden_cross_sma": false,
      "death_cross_sma": false
    }
  ]
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/indicators/AAPL/technical?limit=30" \
  -H "Authorization: Bearer $TOKEN"
```

---

### `GET /api/v1/indicators/{ticker}/risk`

Daily risk metrics: volatility, beta, drawdowns, Sharpe, Sortino, Calmar.

**Response**

```json
{
  "ticker": "AAPL",
  "indicators": [
    {
      "date": "2025-05-02",
      "atr_14": 3.12,
      "hist_vol_20d": 0.184,
      "hist_vol_60d": 0.212,
      "beta_sp500_60d": 1.18,
      "worst_drop_1d": -0.048,
      "worst_drop_5d": -0.071,
      "worst_drop_10d": -0.089,
      "max_drawdown_1y": -0.143,
      "max_drawdown_2y": -0.271,
      "sharpe_60d": 1.42,
      "sortino_60d": 1.87,
      "calmar_1y": 2.31
    }
  ]
}
```

---

### `GET /api/v1/indicators/{ticker}/valuation`

Daily market cap, EV, and valuation multiples alongside price return periods.

**Response**

```json
{
  "ticker": "AAPL",
  "indicators": [
    {
      "date": "2025-05-02",
      "market_cap": 2940000000000,
      "enterprise_value": 2960000000000,
      "pe_ttm": 29.4,
      "forward_pe": 27.1,
      "ps_ttm": 7.8,
      "pb": 45.2,
      "ev_ebitda": 21.3,
      "ev_ebit": 23.1,
      "ev_fcf": 25.4,
      "earnings_yield": 0.034,
      "fcf_yield": 0.039,
      "pct_chg_1w": 1.2,
      "pct_chg_3m": 8.4,
      "pct_chg_6m": 14.1,
      "pct_chg_9m": 18.6,
      "pct_chg_ytd": 10.2,
      "pct_chg_1y": 22.3
    }
  ]
}
```

---

### `GET /api/v1/indicators/{ticker}/returns`

Daily rolling return snapshots over standard periods (1w, 1m, 3m, 6m, 9m, YTD, 1y).

**Response**

```json
{
  "ticker": "AAPL",
  "returns": [
    {
      "date": "2025-05-02",
      "ret_1w": 0.012,
      "ret_1m": 0.041,
      "ret_3m": 0.084,
      "ret_6m": 0.141,
      "ret_9m": 0.186,
      "ret_ytd": 0.102,
      "ret_1y": 0.223,
      "price_field": "adj_close",
      "computed_at": "2025-05-03T01:00:00Z"
    }
  ]
}
```

---

## Analytics

### `GET /api/v1/analytics/snapshots/{ticker}`

Latest combined analytics snapshot for a ticker (price, technicals).

**Scope:** `analytics:read`

**Path parameters**

| Parameter | Description |
|---|---|
| `ticker` | Ticker symbol |

**Response**

```json
{
  "snapshot": {
    "ticker": "AAPL",
    "company_name": "Apple Inc.",
    "last_price": 189.42,
    "price_change_pct": 0.82,
    "rsi_14": 61.3,
    "sma_10": 187.1,
    "sma_50": 182.5,
    "sma_200": 175.0,
    "macd": 1.23,
    "macd_signal": 0.98,
    "macd_hist": 0.25,
    "updated_at": "2025-05-03T14:30:00Z"
  }
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/analytics/snapshots/AAPL" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Signals

### `GET /api/v1/signals/latest`

Latest trading signals with optional ticker filter.

**Scope:** `signals:read`

**Query parameters**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `ticker` | string | No | — | 1–16 chars | Filter to a single ticker |
| `limit` | integer | No | `20` | 1–200 | Max signals to return |

**Response**

```json
{
  "signals": [
    {
      "ticker": "AAPL",
      "strategy_name": "momentum_rsi",
      "signal": "buy",
      "confidence": 0.78,
      "entry_price": 189.42,
      "target_price": 198.0,
      "stop_loss": 183.5,
      "timestamp": "2025-05-03T14:00:00Z"
    }
  ]
}
```

**Example**

```bash
# All latest signals
curl -s "https://api.theeyebeta.store/api/v1/signals/latest?limit=50" \
  -H "Authorization: Bearer $TOKEN"

# Signals for one ticker
curl -s "https://api.theeyebeta.store/api/v1/signals/latest?ticker=AAPL" \
  -H "Authorization: Bearer $TOKEN"
```

---

## News

### `GET /api/v1/news/market`

Latest market-wide news headlines.

**Scope:** `market:read`

**Query parameters**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `limit` | integer | No | `20` | 1–100 | Max articles |

**Response**

```json
{
  "news": [
    {
      "id": 4821,
      "provider": "Reuters",
      "url": "https://...",
      "headline": "Fed holds rates steady...",
      "summary": "The Federal Reserve...",
      "source": "reuters",
      "category": "macro",
      "published_at": "2025-05-03T13:00:00Z"
    }
  ]
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/news/market?limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

---

### `GET /api/v1/news/ticker/{ticker}`

News articles for a specific ticker.

**Scope:** `market:read`

**Path parameters**

| Parameter | Description |
|---|---|
| `ticker` | Ticker symbol |

**Query parameters**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `limit` | integer | No | `20` | 1–100 | Max articles |

**Response**

```json
{
  "ticker": "AAPL",
  "news": [
    {
      "news_id": 1093,
      "source": "Bloomberg",
      "title": "Apple beats earnings estimates...",
      "url": "https://...",
      "published_at": "2025-05-02T21:00:00Z",
      "summary": "Apple Inc. reported quarterly earnings...",
      "sentiment": "positive",
      "sentiment_score": 0.74
    }
  ]
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/news/ticker/AAPL?limit=5" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Reference Data

Static lookup tables. All require `market:read` scope and take no required parameters unless noted.

### `GET /api/v1/reference/countries`

```json
{
  "countries": [
    { "country_code": "US", "country_name": "United States", "default_timezone": "America/New_York" }
  ]
}
```

---

### `GET /api/v1/reference/currencies`

```json
{
  "currencies": [
    { "currency_code": "USD", "currency_name": "US Dollar", "symbol": "$" }
  ]
}
```

---

### `GET /api/v1/reference/exchanges`

```json
{
  "exchanges": [
    {
      "exchange_id": 1,
      "name": "NASDAQ",
      "mic_code": "XNAS",
      "country_code": "US",
      "timezone": "America/New_York"
    }
  ]
}
```

---

### `GET /api/v1/reference/sectors`

```json
{
  "sectors": [
    { "sector_id": 4, "sector_name": "Technology" }
  ]
}
```

---

### `GET /api/v1/reference/industries`

**Query parameters**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `sector_id` | integer | No | Filter industries to a specific sector |

```json
{
  "industries": [
    { "industry_id": 21, "sector_id": 4, "industry_name": "Consumer Electronics" }
  ]
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/reference/industries?sector_id=4" \
  -H "Authorization: Bearer $TOKEN"
```

---

### `GET /api/v1/reference/calendar`

Trading calendar days with market open/close status and holidays.

**Query parameters**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `start` | date (`YYYY-MM-DD`) | No | — | — | Start date inclusive |
| `end` | date (`YYYY-MM-DD`) | No | — | — | End date inclusive |
| `limit` | integer | No | `90` | 1–500 | Max days |

**Response**

```json
{
  "days": [
    {
      "calendar_date": "2025-05-26",
      "is_trading_day": false,
      "market_name": "NYSE",
      "holiday_name": "Memorial Day",
      "notes": null
    }
  ]
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/reference/calendar?start=2025-05-01&end=2025-05-31" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Advisor

AI-backed endpoints. Both paths are equivalent — `/api/v1/advisor/*` and the shorter `/api/v1/*` aliases work identically.

**Scope for all:** `advisor:read`

---

### `GET /api/v1/advisor/context` (alias: `GET /api/v1/context`)

Structured market context payload for feeding into an external AI client — ticker list, recent news, and optional per-ticker snapshot.

**Query parameters**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `ticker` | string | No | — | — | Focus context on a specific ticker (adds snapshot) |
| `ticker_limit` | integer | No | `25` | 1–200 | Max tickers to include in the list |
| `news_limit` | integer | No | `10` | 1–50 | Max news items to include |

**Response**

```json
{
  "tickers": [
    { "ticker": "AAPL", "company_name": "Apple Inc." }
  ],
  "news": [
    {
      "headline": "Fed holds rates steady",
      "source": "Reuters",
      "category": "macro",
      "published_at": "2025-05-03T13:00:00Z"
    }
  ],
  "ticker_snapshot": {
    "ticker": "AAPL",
    "company_name": "Apple Inc.",
    "last_price": 189.42,
    "price_change_pct": 0.82,
    "rsi_14": 61.3,
    "sma_10": 187.1,
    "sma_50": 182.5,
    "sma_200": 175.0,
    "macd": 1.23,
    "macd_signal": 0.98,
    "macd_hist": 0.25,
    "updated_at": "2025-05-03T14:30:00Z"
  }
}
```

> `ticker_snapshot` is `null` when no `ticker` query param is provided.

**Example**

```bash
# General context
curl -s "https://api.theeyebeta.store/api/v1/advisor/context" \
  -H "Authorization: Bearer $TOKEN"

# Focused on AAPL
curl -s "https://api.theeyebeta.store/api/v1/advisor/context?ticker=AAPL&news_limit=5" \
  -H "Authorization: Bearer $TOKEN"
```

---

### `POST /api/v1/advisor/chat` (alias: `POST /api/v1/chat`)

Ask the AI advisor a question. The API pulls relevant DB context and returns an answer.

**Request body**

```json
{
  "question": "What is the RSI trend for AAPL this month?",
  "ticker": "AAPL"
}
```

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `question` | string | Yes | 1–1000 chars | Natural language question |
| `ticker` | string | No | max 16 chars | Optional ticker to focus the context on |

**Response**

```json
{
  "answer": "AAPL's RSI has been rising from 48 to 61 over the past month...",
  "used_ticker": "AAPL",
  "context_rows": 30
}
```

**Example**

```bash
curl -s -X POST "https://api.theeyebeta.store/api/v1/advisor/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Is AAPL currently overbought?", "ticker": "AAPL"}'
```

---

## Portfolio

### `GET /api/v1/portfolio/state`

Current portfolio state including valuation and open positions.

**Scope:** `portfolio:read`

**Query parameters**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `owner_subject` | string | Conditionally | — | 1–128 chars | Required for service principals. User principals are automatically scoped to their own portfolio. |
| `position_limit` | integer | No | `50` | 1–500 | Max positions to return |

> **Ownership rules:**
> - **User tokens**: always return the calling user's portfolio. Passing `owner_subject` for a different user returns `403`.
> - **Service tokens**: `owner_subject` is required and can be any user subject.

**Response**

```json
{
  "owner_subject": "user:abc123",
  "valuation": {
    "valuation_date": "2025-05-02",
    "total_value": 125840.50,
    "cash_balance": 23400.00,
    "positions_value": 102440.50,
    "total_cost_basis": 98000.00,
    "unrealized_pnl": 4440.50,
    "realized_pnl": 1200.00,
    "currency_code": "USD",
    "created_at": "2025-05-02T22:00:00Z"
  },
  "positions": [
    {
      "ticker": "AAPL",
      "company_name": "Apple Inc.",
      "quantity": 50,
      "average_cost": 175.20,
      "last_price": 189.42,
      "market_value": 9471.00,
      "unrealized_pnl": 711.00,
      "last_updated": "2025-05-03T14:30:00Z"
    }
  ]
}
```

**Example**

```bash
# User token — own portfolio
curl -s "https://api.theeyebeta.store/api/v1/portfolio/state" \
  -H "Authorization: Bearer $USER_TOKEN"

# Service token — specify owner
curl -s "https://api.theeyebeta.store/api/v1/portfolio/state?owner_subject=user%3Aabc123" \
  -H "Authorization: Bearer $SERVICE_TOKEN"
```

---

## Generic Data Tables

Read-only metadata and row access for canonical `theeyebeta` tables.

**Scope:** any basic read scope for basic market-data tables; `admin:read` for all `theeyebeta` tables/views.

### `GET /api/v1/data/tables`

List readable tables for the authenticated principal.

### `GET /api/v1/data/tables/{table}/columns`

Return column names and types for one readable table.

### `GET /api/v1/data/tables/{table}/rows`

Return paged rows from one readable table.

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `limit` | integer | No | `100` | 1–1000 rows |
| `offset` | integer | No | `0` | Page offset |
| `order_by` | string | No | inferred | Column to sort by |
| `order_dir` | string | No | `desc` | `asc` or `desc` |
| `filter` | string[] | No | — | Repeatable `column:op:value`; ops: `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `like`, `ilike` |
| `symbol` | string | No | — | Resolves through `instrument_id`, legacy `ticker_id`, or a `symbol` column |
| `date_column` | string | No | inferred | Date/timestamp column for `start`/`end` |
| `start` | date | No | — | Inclusive lower date bound |
| `end` | date | No | — | Inclusive upper date bound |

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/data/tables/latest_snapshots/rows?symbol=AAPL&limit=5" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Admin

All admin endpoints require `admin:read` scope. The HTML dashboard page is the only exception — it is served without auth (auth is handled client-side via token input in the UI).

---

### `GET /api/v1/admin/dashboard`

Serves the admin dashboard as an HTML page. Open in a browser, paste a bearer token with `admin:read` scope, and click **Connect**.

No auth header required for this endpoint.

---

### `GET /api/v1/admin/dashboard-data`

Returns all dashboard data as a single JSON payload (what the HTML dashboard consumes internally).

**Scope:** `admin:read`

**Response fields**

| Field | Type | Description |
|---|---|---|
| `timestamp` | datetime | Data fetch time |
| `api` | object | API server status (name, version, environment, host, port) |
| `database` | object | DB connection status and masked URL |
| `active_tickers` | integer | Count of active tickers |
| `engine_workers` | array | Worker heartbeat rows |
| `tables` | array | Table name + row count pairs |
| `service_clients` | array | Registered service clients |
| `recent_events` | array | Most recent audit events |

---

### `GET /api/v1/admin/audit-events`

Paginated audit event log.

**Scope:** `admin:read`

**Query parameters**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `limit` | integer | No | `50` | 1–500 | Max events |
| `category` | string | No | — | max 80 chars | Filter by event category |

**Response**

```json
{
  "events": [
    {
      "event_id": "evt_abc123",
      "event_type": "trade.placed",
      "event_category": "trades",
      "source_type": "service",
      "source_id": "vi-app",
      "target_type": "order",
      "target_id": "ord_8f3a2c1b",
      "severity": "info",
      "payload": {},
      "created_at": "2025-05-03T14:35:00Z"
    }
  ]
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/admin/audit-events?limit=20&category=trades" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

### `GET /api/v1/admin/named-query`

Execute a server-curated read-only query against `theeyebeta`.

**Scope:** `admin:read`

**Query parameters**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `query_name` | string | Yes | — | 1–80 chars | Curated query name |
| `limit` | integer | No | `100` | 1–1000 | Max rows returned |

Available query names: `all_tickers`, `latest_prices`, `latest_signals`,
`orders`, `portfolio`, `command_log`, `market_news`, `heartbeats`, `table_stats`.

**Response**

```json
{
  "query_name": "all_tickers",
  "row_count": 3,
  "rows": [
    { "ticker": "AAPL", "company_name": "AAPL", "is_active": true }
  ]
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/admin/named-query?query_name=all_tickers&limit=5" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

### `GET /api/v1/admin/etl-jobs`

State of all registered ETL/data-pipeline jobs.

**Scope:** `admin:read`

**Response**

```json
{
  "jobs": [
    {
      "job_name": "price_ingestion",
      "last_run_at": "2025-05-03T14:00:00Z",
      "last_successful_date": "2025-05-03",
      "status": "success",
      "last_error": null
    }
  ]
}
```

---

### `GET /api/v1/admin/engine-status`

Key-value engine status entries from the data engine.

**Scope:** `admin:read`

**Response**

```json
{
  "entries": [
    {
      "key": "last_price_run",
      "value": "2025-05-03T14:00:00Z",
      "updated_at": "2025-05-03T14:00:01Z"
    }
  ]
}
```

---

### `GET /api/v1/admin/worker-heartbeats`

Latest heartbeat records for engine worker processes.

**Scope:** `admin:read`

**Response**

```json
{
  "workers": [
    {
      "worker_id": "price-worker-1",
      "worker_type": "price_ingestion",
      "status": "running",
      "last_heartbeat": "2025-05-03T14:34:50Z",
      "started_at": "2025-05-03T06:00:00Z",
      "restart_count": 0,
      "last_error": null
    }
  ]
}
```

---

### `GET /api/v1/admin/price-ticks/{ticker}`

Recent intraday price tick records for a ticker (raw ingestion data).

**Scope:** `admin:read`

**Path parameters**

| Parameter | Description |
|---|---|
| `ticker` | Ticker symbol |

**Query parameters**

| Parameter | Type | Required | Default | Constraints | Description |
|---|---|---|---|---|---|
| `limit` | integer | No | `100` | 1–1000 | Max ticks |

**Response**

```json
{
  "ticker": "AAPL",
  "ticks": [
    {
      "tick_id": 98421,
      "ts": "2025-05-03T14:34:45Z",
      "price": 189.42,
      "open": 188.10,
      "high": 190.55,
      "low": 187.60,
      "close": 189.42,
      "volume": 123400,
      "source": "feed_primary"
    }
  ]
}
```

**Example**

```bash
curl -s "https://api.theeyebeta.store/api/v1/admin/price-ticks/AAPL?limit=10" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```
