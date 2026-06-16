export type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type TokenRequest = {
  requested_scopes?: string[];
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_minutes: number;
  scopes: string[];
};

export type ChatRequest = {
  question: string;
  ticker?: string | null;
};

export type ChatResponse = {
  answer: string;
  used_ticker: string | null;
  context_rows: number;
};

export type HealthResponse = {
  status: "healthy" | "degraded";
  database: boolean;
};

export type DataTableInfo = {
  name: string;
  table_type: string;
  row_count_estimate: number | null;
  basic_access: boolean;
};

export type DataTablesResponse = {
  tables: DataTableInfo[];
};

export type DataColumnInfo = {
  name: string;
  data_type: string;
  nullable: boolean;
  ordinal_position: number;
};

export type DataColumnsResponse = {
  table: string;
  columns: DataColumnInfo[];
};

export type DataRowsResponse<T extends Record<string, unknown> = Record<string, unknown>> = {
  table: string;
  limit: number;
  offset: number;
  row_count: number;
  rows: T[];
};

export type DataRowsQuery = {
  limit?: number;
  offset?: number;
  order_by?: string;
  order_dir?: "asc" | "desc";
  filter?: string | string[];
  symbol?: string;
  date_column?: string;
  start?: string;
  end?: string;
};

export type RootResponse = {
  name: string;
  version: string;
  status: string;
};

export type DataApiClientConfig = {
  baseUrl: string;
  bearerToken?: string;
  serviceClientId?: string;
  serviceClientSecret?: string;
  requestedScopes?: string[];
  fetchImpl?: FetchLike;
};

type QueryValue = string | number | boolean | null | undefined | Array<string | number | boolean>;
type QueryParams = Record<string, QueryValue>;

export class DataApiClient {
  private readonly baseUrl: string;
  private readonly bearerToken?: string;
  private readonly serviceClientId?: string;
  private readonly serviceClientSecret?: string;
  private readonly requestedScopes: string[];
  private readonly fetchImpl: FetchLike;
  private _cachedServiceToken: string | null = null;
  private _cachedServiceTokenExpiresAt = 0;

  constructor(config: DataApiClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/+$/, "");
    this.bearerToken = config.bearerToken;
    this.serviceClientId = config.serviceClientId;
    this.serviceClientSecret = config.serviceClientSecret;
    this.requestedScopes = config.requestedScopes ?? [];
    if (config.fetchImpl) {
      this.fetchImpl = config.fetchImpl;
    } else if (typeof fetch !== "undefined") {
      this.fetchImpl = fetch.bind(globalThis);
    } else {
      throw new Error("No fetch implementation available. Provide fetchImpl in config.");
    }
  }

  withBearerToken(token: string): DataApiClient {
    return new DataApiClient({
      baseUrl: this.baseUrl,
      bearerToken: token,
      serviceClientId: this.serviceClientId,
      serviceClientSecret: this.serviceClientSecret,
      requestedScopes: this.requestedScopes,
      fetchImpl: this.fetchImpl,
    });
  }

  async root(): Promise<RootResponse> {
    return this.request<RootResponse>("GET", "/");
  }

  async health(): Promise<HealthResponse> {
    return this.request<HealthResponse>("GET", "/health");
  }

  async issueToken(payload: TokenRequest): Promise<TokenResponse> {
    return this.request<TokenResponse>("POST", "/api/v1/auth/service-token", { body: payload });
  }

  async context(params: { ticker?: string; ticker_limit?: number; news_limit?: number } = {}): Promise<unknown> {
    return this.request<unknown>("GET", "/api/v1/context", { query: params });
  }

  async chat(payload: ChatRequest): Promise<ChatResponse> {
    return this.request<ChatResponse>("POST", "/api/v1/chat", { body: payload });
  }

  async listTables(): Promise<DataTablesResponse> {
    return this.request<DataTablesResponse>("GET", "/api/v1/data/tables");
  }

  async getTableColumns(table: string): Promise<DataColumnsResponse> {
    return this.request<DataColumnsResponse>("GET", `/api/v1/data/tables/${encodeURIComponent(table)}/columns`);
  }

  async queryTableRows<T extends Record<string, unknown> = Record<string, unknown>>(
    table: string,
    query: DataRowsQuery = {},
  ): Promise<DataRowsResponse<T>> {
    return this.request<DataRowsResponse<T>>(
      "GET",
      `/api/v1/data/tables/${encodeURIComponent(table)}/rows`,
      { query },
    );
  }

  async get<T>(path: string, query?: QueryParams): Promise<T> {
    return this.request<T>("GET", path, { query });
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>("POST", path, { body });
  }

  private async request<T>(
    method: "GET" | "POST",
    path: string,
    options: { body?: unknown; query?: QueryParams } = {},
  ): Promise<T> {
    const url = this.buildUrl(path, options.query);
    const headers: Record<string, string> = {
      Accept: "application/json",
    };
    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    headers.Authorization = `Bearer ${await this.getAuthorizationToken()}`;

    const resp = await this.fetchImpl(url, {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });

    const rawBody = await resp.text();
    if (!resp.ok) {
      throw new Error(`Data API ${method} ${path} failed (${resp.status}): ${rawBody}`);
    }
    if (!rawBody) {
      return {} as T;
    }
    try {
      return JSON.parse(rawBody) as T;
    } catch {
      throw new Error(`Data API ${method} ${path} returned non-JSON response: ${rawBody}`);
    }
  }

  private buildUrl(path: string, query?: QueryParams): string {
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    const url = new URL(`${this.baseUrl}${normalizedPath}`);
    if (!query) {
      return url.toString();
    }
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null) {
        continue;
      }
      if (Array.isArray(value)) {
        for (const item of value) {
          url.searchParams.append(key, String(item));
        }
      } else {
        url.searchParams.set(key, String(value));
      }
    }
    return url.toString();
  }

  private async getAuthorizationToken(): Promise<string> {
    if (this.bearerToken) {
      return this.bearerToken;
    }
    const now = Date.now();
    if (this._cachedServiceToken && now < this._cachedServiceTokenExpiresAt) {
      return this._cachedServiceToken;
    }
    if (!this.serviceClientId || !this.serviceClientSecret) {
      throw new Error("Provide bearerToken or serviceClientId/serviceClientSecret");
    }

    const basic = toBase64(`${this.serviceClientId}:${this.serviceClientSecret}`);
    const response = await this.fetchImpl(`${this.baseUrl}/api/v1/auth/service-token`, {
      method: "POST",
      headers: {
        Authorization: `Basic ${basic}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ requested_scopes: this.requestedScopes }),
    });
    const rawBody = await response.text();
    if (!response.ok) {
      throw new Error(`Service token request failed (${response.status}): ${rawBody}`);
    }
    let parsed: { access_token: string; expires_minutes: number };
    try {
      parsed = JSON.parse(rawBody) as { access_token: string; expires_minutes: number };
    } catch {
      throw new Error(`Service token response was not JSON: ${rawBody}`);
    }
    this._cachedServiceToken = parsed.access_token;
    this._cachedServiceTokenExpiresAt = Date.now() + Math.max(1, parsed.expires_minutes - 1) * 60 * 1000;
    return this._cachedServiceToken;
  }
}

export function createDataApiPlugin(config: DataApiClientConfig): DataApiClient {
  return new DataApiClient(config);
}

function toBase64(value: string): string {
  if (typeof btoa === "function") {
    return btoa(value);
  }
  if (typeof Buffer !== "undefined") {
    return Buffer.from(value, "utf-8").toString("base64");
  }
  throw new Error("No base64 encoder available in this runtime");
}
