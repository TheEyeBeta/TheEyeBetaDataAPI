type CallResult = {
  ok: boolean;
  data: string;
};

function byId<T extends HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) {
    throw new Error(`Missing required element: ${id}`);
  }
  return el as T;
}

async function call(url: string): Promise<CallResult> {
  try {
    const resp = await fetch(url);
    const text = await resp.text();
    try {
      return { ok: resp.ok, data: JSON.stringify(JSON.parse(text), null, 2) };
    } catch {
      return { ok: resp.ok, data: text };
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown network error";
    return { ok: false, data: `Network error: ${message}` };
  }
}

function show(elId: string, result: CallResult): void {
  const el = byId<HTMLPreElement>(elId);
  el.textContent = result.data;
  el.className = result.ok ? "" : "error";
}

function inputValue(id: string): string {
  return byId<HTMLInputElement>(id).value.trim();
}

async function checkHealth(): Promise<void> {
  const result = await call("/api/health");
  show("health-out", result);
  const dot = byId<HTMLSpanElement>("health-dot");
  const text = byId<HTMLSpanElement>("health-text");
  if (result.ok) {
    dot.className = "status-dot ok";
    text.textContent = "API is healthy";
  } else {
    dot.className = "status-dot fail";
    text.textContent = "API is unreachable";
  }
}

function wireUi(): void {
  byId<HTMLButtonElement>("btn-health").addEventListener("click", () => void checkHealth());
  byId<HTMLButtonElement>("btn-tickers").addEventListener("click", () => {
    void call("/api/tickers").then((result) => show("tickers-out", result));
  });
  byId<HTMLButtonElement>("btn-ai-ticker").addEventListener("click", () => {
    const ticker = inputValue("ai-ticker-in") || "AAPL";
    void call(`/api/ai/ticker/${encodeURIComponent(ticker)}`).then((result) => show("ai-ticker-out", result));
  });
  byId<HTMLButtonElement>("btn-technical").addEventListener("click", () => {
    const ticker = inputValue("tech-ticker-in") || "AAPL";
    void call(`/api/indicators/${encodeURIComponent(ticker)}/technical`).then((result) => show("tech-out", result));
  });
  byId<HTMLButtonElement>("btn-fundamentals").addEventListener("click", () => {
    const ticker = inputValue("fund-ticker-in") || "AAPL";
    void call(`/api/fundamentals/${encodeURIComponent(ticker)}/income`).then((result) => show("fund-out", result));
  });
  byId<HTMLButtonElement>("btn-risk").addEventListener("click", () => {
    const ticker = inputValue("risk-ticker-in") || "AAPL";
    void call(`/api/indicators/${encodeURIComponent(ticker)}/risk`).then((result) => show("risk-out", result));
  });
  byId<HTMLButtonElement>("btn-ai-context").addEventListener("click", () => {
    void call("/api/ai/context").then((result) => show("ai-ctx-out", result));
  });
  byId<HTMLButtonElement>("btn-ai-signals").addEventListener("click", () => {
    void call("/api/ai/signals").then((result) => show("ai-signals-out", result));
  });
  byId<HTMLButtonElement>("btn-ai-portfolio").addEventListener("click", () => {
    void call("/api/ai/portfolio").then((result) => show("ai-portfolio-out", result));
  });
  byId<HTMLButtonElement>("btn-news-latest").addEventListener("click", () => {
    void call("/api/news/latest").then((result) => show("news-out", result));
  });
  byId<HTMLButtonElement>("btn-news-stats").addEventListener("click", () => {
    void call("/api/news/stats").then((result) => show("news-stats-out", result));
  });
  byId<HTMLButtonElement>("btn-chart-prices").addEventListener("click", () => {
    const ticker = inputValue("chart-ticker-in") || "AAPL";
    void call(`/api/charting/${encodeURIComponent(ticker)}/prices`).then((result) => show("chart-out", result));
  });
}

wireUi();
void checkHealth();
