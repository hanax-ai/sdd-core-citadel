# SDD-Core CITADEL — local bridge

Copy `bridge/bridge.py` into `Amigos-Agents/harness/bridge.py`.

```bash
pip install fastapi uvicorn sse-starlette pydantic python-dotenv
export ANTHROPIC_API_KEY=... OPENAI_API_KEY=... GEMINI_API_KEY=...
export AMIGO_TARGET_DIR=/path/to/target/repo
export BRIDGE_API_KEY=some-long-random-string
python harness/bridge.py          # http://127.0.0.1:8000
```

## Auth

Every route requires a shared secret, checked against the `BRIDGE_API_KEY`
env var with a constant-time comparison (`hmac.compare_digest`). This is a
bridge-level addition, not part of the harness's own contract -- it exists
because the bridge listens on a local TCP port with no other access control.

- `BRIDGE_API_KEY` (required) -- the shared secret. The server refuses to
  start (fails fast, same pattern as the provider key checks in
  `harness/llm_clients.py`) if this is unset.
- Every request must send `X-Bridge-Key: <the same value>` as a request
  header, or the bridge responds `401 Unauthorized`.
- Every route also accepts the key as a `?key=` query param instead of the
  header (the header wins if both are present). This exists for
  `GET /api/stream/{run_id}`: browsers' native `EventSource` API cannot set
  custom request headers, so the dashboard's `new EventSource(url)` call
  authenticates via `?key=` instead.

## target_dir allowlist

`target_dir` on `POST /api/run-task` is resolved and checked against an
allowlist before use -- it is never trusted as-is.

- `BRIDGE_ALLOWED_TARGET_DIRS` (optional) -- comma-separated absolute paths.
  A requested `target_dir` must resolve to one of these roots or a
  subdirectory of one of them, or the request is rejected with `400
  TARGET_NOT_ALLOWED`.
- If unset, the allowlist defaults to just `harness.config.DEFAULT_TARGET_DIR`.

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
