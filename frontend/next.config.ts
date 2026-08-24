import type { NextConfig } from "next";

const exportarEstatico = process.env.STATIC_EXPORT === "true";

const config: NextConfig = {
  reactStrictMode: true,
  ...(exportarEstatico
    ? {
        output: "export",
        trailingSlash: true,
        images: { unoptimized: true },
      }
    : {}),
  // La API vive aparte. En desarrollo se proxea para que el navegador vea un solo
  // origen y la cookie del refresh token viaje sin líos de CORS.
  ...(!exportarEstatico
    ? {
        async rewrites() {
          const api = process.env.API_URL ?? "http://localhost:8000";
          return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
        },
      }
    : {}),
};

export default config;
