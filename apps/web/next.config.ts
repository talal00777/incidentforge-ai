import type { NextConfig } from "next";

const upstream = process.env.INTERNAL_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${upstream}/api/v1/:path*` },
      { source: "/health/:path*", destination: `${upstream}/health/:path*` },
    ];
  },
};

export default nextConfig;
