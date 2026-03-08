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

async function call(url: string, init?: RequestInit): Promise<CallResult> {
  try {
    const resp = await fetch(url, init);
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

  byId<HTMLButtonElement>("btn-symbol-search").addEventListener("click", () => {
    const query = inputValue("symbols-query-in") || "AAP";
    void call(`/api/symbols/search?q=${encodeURIComponent(query)}&limit=25`).then((result) =>
      show("symbols-out", result),
    );
  });

  byId<HTMLButtonElement>("btn-quotes").addEventListener("click", () => {
    const symbols = inputValue("quotes-symbols-in") || "AAPL,MSFT";
    void call(`/api/market-data/quotes?symbols=${encodeURIComponent(symbols)}`).then((result) =>
      show("quotes-out", result),
    );
  });

  byId<HTMLButtonElement>("btn-analytics").addEventListener("click", () => {
    const ticker = inputValue("analytics-ticker-in") || "AAPL";
    void call(`/api/analytics/${encodeURIComponent(ticker)}`).then((result) => show("analytics-out", result));
  });

  byId<HTMLButtonElement>("btn-advisor-context").addEventListener("click", () => {
    const ticker = inputValue("context-ticker-in");
    const tickerQuery = ticker ? `&ticker=${encodeURIComponent(ticker)}` : "";
    void call(`/api/advisor/context?ticker_limit=25&news_limit=10${tickerQuery}`).then((result) =>
      show("advisor-context-out", result),
    );
  });

  byId<HTMLButtonElement>("btn-advisor-chat").addEventListener("click", () => {
    const ticker = inputValue("chat-ticker-in") || "AAPL";
    const question = inputValue("chat-question-in") || "Give me a quick snapshot.";
    void call("/api/advisor/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, ticker }),
    }).then((result) => show("advisor-chat-out", result));
  });

  byId<HTMLButtonElement>("btn-signals").addEventListener("click", () => {
    void call("/api/signals/latest").then((result) => show("signals-out", result));
  });

  byId<HTMLButtonElement>("btn-portfolio").addEventListener("click", () => {
    const ownerSubject = inputValue("portfolio-owner-in");
    const ownerQuery = ownerSubject ? `?owner_subject=${encodeURIComponent(ownerSubject)}` : "";
    void call(`/api/portfolio/state${ownerQuery}`).then((result) => show("portfolio-out", result));
  });
}

wireUi();
void checkHealth();
