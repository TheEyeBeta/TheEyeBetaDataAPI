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
  serviceClientId: process.env.SERVICE_CLIENT_ID,
  serviceClientSecret: process.env.SERVICE_CLIENT_SECRET,
  requestedScopes: ["advisor:read", "market:read"],
});

const health = await client.health();
const context = await client.context({ ticker: "AAPL" });
const answer = await client.chat({ question: "Give me a quick AAPL snapshot", ticker: "AAPL" });
```

## Build

```bash
npm install
npm run build
```
