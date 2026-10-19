import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'export', images: { unoptimized: true }, agentRules: false,
  ...(process.env.INTRASPOT_FRONTEND_PROFILE === 'real' ? {distDir: 'out-real'} : {}),
};

export default nextConfig;
