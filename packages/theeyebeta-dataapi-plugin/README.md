# @theeyebeta/dataapi-plugin

TypeScript client plugin for integrating TheEyeBetaDataAPI into other repositories.

## Install

From a published package:

```bash
npm install @theeyebeta/dataapi-plugin
```

From GitHub repo directly:

```bash
npm install github:<YOUR_GITHUB_USER>/<YOUR_REPO>#main
```

From local path:

```bash
npm install ../TheEyeBetaDataAPI/packages/theeyebeta-dataapi-plugin
```

## Usage

```ts
import { createDataApiPlugin } from "@theeyebeta/dataapi-plugin";

const client = createDataApiPlugin({
  baseUrl: "https://api.theeyebeta.store",
  apiKey: process.env.DATA_API_KEY,
});

const health = await client.health();
const token = await client.issueToken({ subject: "my-service", expires_minutes: 60 });
const authed = client.withBearerToken(token.access_token);
const answer = await authed.chat({ question: "Give me a quick AAPL snapshot", ticker: "AAPL" });
```

## Build

```bash
npm install
npm run build
```
