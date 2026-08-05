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
      // Legacy manager bookmarks now enter the Next command centre.
      { source: "/manager", destination: "/home", permanent: false },
    ];
  },
  // The browser always talks to its current AGRO CEO origin. Vercel rewrites
  // those calls to the FastAPI kernel so the kernel remains the source of
  // truth and its signed cookies are never handled by client JavaScript.
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${apiOrigin}/api/v1/:path*` },
      { source: "/health", destination: `${apiOrigin}/health` },
      // Native field capture is intentionally retained as a small, signed
      // PWA compatibility surface until its dedicated Next replacement is
      // ready. It stays on the public web origin, so capture passes and the
      // existing service-worker scope continue to work without a new host.
      { source: "/field", destination: `${apiOrigin}/field` },
      { source: "/field-service-worker.js", destination: `${apiOrigin}/field-service-worker.js` },
      { source: "/assets/field.css", destination: `${apiOrigin}/assets/field.css` },
      { source: "/assets/field.js", destination: `${apiOrigin}/assets/field.js` },
      { source: "/assets/rice-sheaf-icon.png", destination: `${apiOrigin}/assets/rice-sheaf-icon.png` },
      { source: "/favicon.png", destination: `${apiOrigin}/favicon.png` },
      { source: "/brand/apple-touch-icon.png", destination: `${apiOrigin}/brand/apple-touch-icon.png` },
      { source: "/site.webmanifest", destination: `${apiOrigin}/site.webmanifest` },
    ];
  },
};

export default nextConfig;
