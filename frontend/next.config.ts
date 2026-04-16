import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Rewrites use a dev-server HTTP proxy whose default timeout is 30s.
  // Callout recommendations can take 45-60s on CPU-only Ollama inference,
  // so raise it above the backend's own ollama_timeout (90s) to avoid 500s.
  experimental: {
    proxyTimeout: 120_000,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
