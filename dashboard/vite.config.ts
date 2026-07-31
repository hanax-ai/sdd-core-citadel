// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

export default defineConfig({
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
  vite: {
    server: {
      proxy: {
        // Dev-only proxy to harness/bridge.py (see harness/BRIDGE_README.md).
        // Set the bridge URL in the header toggle to "" / "/" to use this.
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: true,
          ws: true,
          configure: (proxy) => {
            // Force identity encoding on the proxied request so the bridge never
            // compresses the response in the first place. SSE bodies must not be
            // gzip/br-compressed — stripping content-encoding after the fact
            // without decompressing the body would leave the browser trying to
            // parse compressed bytes as an event stream.
            proxy.on("proxyReq", (proxyReq) => {
              proxyReq.setHeader("Accept-Encoding", "identity");
            });
            proxy.on("proxyRes", (proxyRes) => {
              if (String(proxyRes.headers["content-type"]).includes("text/event-stream")) {
                proxyRes.headers["cache-control"] = "no-cache, no-transform";
              }
            });
          },
        },
      },
    },
  },
});
