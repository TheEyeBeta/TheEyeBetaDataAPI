import express, { type Request, type Response } from "express";
import fetch, { type RequestInit } from "node-fetch";
import path from "path";
import { fileURLToPath } from "url";
import dotenv from "dotenv";

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, "../public")));

const DATA_API_BASE_URL = process.env.DATA_API_BASE_URL || "http://127.0.0.1:7000";
const SERVICE_CLIENT_ID = process.env.SERVICE_CLIENT_ID || "";
const SERVICE_CLIENT_SECRET = process.env.SERVICE_CLIENT_SECRET || "";
const SERVICE_REQUESTED_SCOPES =
  process.env.SERVICE_REQUESTED_SCOPES || "advisor:read market:read symbols:read analytics:read";
const SERVICE_SCOPES = SERVICE_REQUESTED_SCOPES.split(/\s+/).filter(Boolean);

let cachedServiceToken: string | null = null;
let cachedServiceTokenExpiresAt = 0;

console.log(`Proxying to Data API at: ${DATA_API_BASE_URL}`);

async function getServiceBearerToken(): Promise<string> {
  const now = Date.now();
  if (cachedServiceToken && now < cachedServiceTokenExpiresAt) {
    return cachedServiceToken;
  }

  if (!SERVICE_CLIENT_ID || !SERVICE_CLIENT_SECRET) {
    throw new Error("SERVICE_CLIENT_ID and SERVICE_CLIENT_SECRET must be set");
  }

  const basic = Buffer.from(`${SERVICE_CLIENT_ID}:${SERVICE_CLIENT_SECRET}`).toString("base64");
  const tokenResp = await fetch(`${DATA_API_BASE_URL}/api/v1/auth/service-token`, {
    method: "POST",
    headers: {
      Authorization: `Basic ${basic}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ requested_scopes: SERVICE_SCOPES }),
  });
  const rawBody = await tokenResp.text();

  if (!tokenResp.ok) {
    throw new Error(`Failed to fetch service token (${tokenResp.status}): ${rawBody}`);
  }

  const payload = JSON.parse(rawBody) as { access_token: string; expires_minutes: number };
  cachedServiceToken = payload.access_token;
  const expiresMs = Math.max(1, payload.expires_minutes - 1) * 60 * 1000;
  cachedServiceTokenExpiresAt = now + expiresMs;
  return cachedServiceToken;
}

async function proxyJson(res: Response, targetUrl: string, options: RequestInit = {}): Promise<void> {
  try {
    const token = await getServiceBearerToken();
    options.headers = { ...(options.headers || {}), Authorization: `Bearer ${token}` };

    const resp = await fetch(targetUrl, options);
    const text = await resp.text();

    try {
      const json = JSON.parse(text);
      res.status(resp.status).json(json);
    } catch {
      res.status(resp.status).send(text);
    }
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Unknown proxy error";
    console.error("Proxy error:", detail);
    res.status(500).json({ error: "Proxy error", detail });
  }
}

app.get("/api/health", async (_req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/health`);
});

app.get("/api/symbols/search", async (req: Request, res: Response) => {
  const q = String(req.query.q || "AAPL");
  const limit = String(req.query.limit || "25");
  await proxyJson(
    res,
    `${DATA_API_BASE_URL}/api/v1/symbols/search?q=${encodeURIComponent(q)}&limit=${encodeURIComponent(limit)}`,
  );
});

app.get("/api/market-data/quotes", async (req: Request, res: Response) => {
  const symbols = String(req.query.symbols || "AAPL,MSFT");
  await proxyJson(
    res,
    `${DATA_API_BASE_URL}/api/v1/market-data/quotes?symbols=${encodeURIComponent(symbols)}`,
  );
});

app.get("/api/analytics/:ticker", async (req: Request, res: Response) => {
  await proxyJson(
    res,
    `${DATA_API_BASE_URL}/api/v1/analytics/snapshots/${encodeURIComponent(req.params.ticker)}`,
  );
});

app.get("/api/advisor/context", async (req: Request, res: Response) => {
  const ticker = req.query.ticker ? `ticker=${encodeURIComponent(String(req.query.ticker))}&` : "";
  const tickerLimit = `ticker_limit=${encodeURIComponent(String(req.query.ticker_limit || "25"))}`;
  const newsLimit = `news_limit=${encodeURIComponent(String(req.query.news_limit || "10"))}`;
  await proxyJson(
    res,
    `${DATA_API_BASE_URL}/api/v1/advisor/context?${ticker}${tickerLimit}&${newsLimit}`,
  );
});

app.post("/api/advisor/chat", async (req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/api/v1/advisor/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: req.body?.question || "",
      ticker: req.body?.ticker || null,
    }),
  });
});

app.get("/api/signals/latest", async (_req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/api/v1/signals/latest`);
});

app.get("/api/portfolio/state", async (req: Request, res: Response) => {
  const owner = req.query.owner_subject ? `?owner_subject=${encodeURIComponent(String(req.query.owner_subject))}` : "";
  await proxyJson(res, `${DATA_API_BASE_URL}/api/v1/portfolio/state${owner}`);
});

const port = Number(process.env.PORT || 3000);
app.listen(port, () => {
  console.log(`Frontend listening on http://localhost:${port}`);
});
