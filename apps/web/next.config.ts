import type { NextConfig } from "next";

const apiOrigin = (process.env.FFL_API_ORIGIN || "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async redirects() {
    return [
      {
        source: "/:path*",
        has: [{ type: "host", value: "agroceo.co" }],
        destination: "https://www.agroceo.co/:path*",
        permanent: true,
        basePath: false,
      },
    ];
  },
  // The browser always talks to its current AGRO CEO origin. Vercel rewrites
  // those calls to the FastAPI kernel so the kernel remains the source of
  // truth and its signed cookies are never handled by client JavaScript.
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${apiOrigin}/api/v1/:path*` },
      { source: "/health", destination: `${apiOrigin}/health` },
    ];
  },
};

export default nextConfig;
