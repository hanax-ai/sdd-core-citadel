# SDD-Core CITADEL — local bridge

Copy `bridge/bridge.py` into `Amigos-Agents/harness/bridge.py`.

```bash
pip install fastapi uvicorn sse-starlette pydantic python-dotenv
export ANTHROPIC_API_KEY=... OPENAI_API_KEY=... GEMINI_API_KEY=...
export AMIGO_TARGET_DIR=/path/to/target/repo
python harness/bridge.py          # http://127.0.0.1:8000
```

## Vite proxy (mounting CITADEL in `Amigos-Agents/dashboard/`)

Add to `dashboard/vite.config.ts` so the UI can call the bridge same-origin
(then set the bridge URL in the header toggle to an empty string / `/`):

```ts
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

export default defineConfig({
  tanstackStart: { server: { entry: "server" } },
  vite: {
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          ws: true,
          // SSE must not be buffered or compressed
          configure: (proxy) => {
            proxy.on("proxyRes", (proxyRes) => {
              if (String(proxyRes.headers["content-type"]).includes("text/event-stream")) {
                proxyRes.headers["cache-control"] = "no-cache, no-transform";
                delete proxyRes.headers["content-encoding"];
              }
            });
          },
        },
      },
    },
  },
});
```

Plain Vite (non-Lovable config) equivalent:

```ts
import { defineConfig } from "vite";

export default defineConfig({
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
```
