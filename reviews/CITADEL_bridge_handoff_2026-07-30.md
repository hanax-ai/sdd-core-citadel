CITADEL is finalized — copy bridge/bridge.py into your harness and flip the header toggle to Live Bridge.

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
          configure: (proxy) => {
            proxy.on("proxyRes", (res) => {
              if (String(res.headers["content-type"]).includes("text/event-stream")) {
                res.headers["cache-control"] = "no-cache, no-transform";
                delete res.headers["content-encoding"]; // never buffer/compress SSE
              }
            });
          },
        },
      },
    },
  },
});
