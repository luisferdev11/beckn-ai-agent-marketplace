import type { NextConfig } from "next";

const BAP_URL = process.env.BAP_URL ?? "http://localhost:3001";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/bap/:path*",
        destination: `${BAP_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
