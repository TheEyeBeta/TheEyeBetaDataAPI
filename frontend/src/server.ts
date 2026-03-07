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

// Backend API running on the same machine.
const DATA_API_BASE_URL = process.env.DATA_API_BASE_URL || "http://127.0.0.1:7000";
const API_KEY = process.env.DATA_API_KEY || "";

console.log(`Proxying to Data API at: ${DATA_API_BASE_URL}`);

async function proxyJson(res: Response, targetUrl: string, options: RequestInit = {}): Promise<void> {
  try {
    if (API_KEY) {
      options.headers = { ...(options.headers || {}), "X-API-Key": API_KEY };
    }
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

app.get("/api/tickers", async (_req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/api/v1/tickers/`);
});

app.get("/api/tickers/:ticker", async (req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/api/v1/tickers/${encodeURIComponent(req.params.ticker)}`);
});

app.get("/api/indicators/:ticker/technical", async (req: Request, res: Response) => {
  await proxyJson(
    res,
    `${DATA_API_BASE_URL}/api/v1/indicators/${encodeURIComponent(req.params.ticker)}/technical`,
  );
});

app.get("/api/indicators/:ticker/risk", async (req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/api/v1/indicators/${encodeURIComponent(req.params.ticker)}/risk`);
});

app.get("/api/fundamentals/:ticker/income", async (req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/api/v1/fundamentals/${encodeURIComponent(req.params.ticker)}/income`);
});

app.get("/api/charting/:ticker/prices", async (req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/api/v1/charting/${encodeURIComponent(req.params.ticker)}/prices`);
});

app.get("/api/ai/context", async (_req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/api/v1/ai/context`);
});

app.get("/api/ai/signals", async (_req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/api/v1/ai/signals`);
});

app.get("/api/ai/portfolio", async (_req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/api/v1/ai/portfolio`);
});

app.get("/api/ai/ticker/:ticker", async (req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/api/v1/ai/ticker/${encodeURIComponent(req.params.ticker)}`);
});

app.get("/api/news/latest", async (_req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/api/news/latest`);
});

app.get("/api/news/stats", async (_req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/api/news/stats`);
});

app.get("/api/news", async (_req: Request, res: Response) => {
  await proxyJson(res, `${DATA_API_BASE_URL}/api/news/`);
});

const port = Number(process.env.PORT || 3000);
app.listen(port, () => {
  console.log(`Frontend listening on http://localhost:${port}`);
});
