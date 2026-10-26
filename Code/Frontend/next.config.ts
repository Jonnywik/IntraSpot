import { existsSync } from 'node:fs';
import type { NextConfig } from "next";
import { getFrontendDeployment, resolveHostedConfig } from './lib/auth-storage';

const deployment = getFrontendDeployment(process.env.NEXT_PUBLIC_DEPLOYMENT);
if (!deployment) throw new Error('Frontend deployment mode is invalid.');

if (deployment === 'hosted') {
  const nextEnvironmentFiles = ['.env', '.env.production', '.env.production.local', '.env.local'];
  if (
    process.env.INTRASPOT_HOSTED_BUILD_GUARD !== 'verified' ||
    nextEnvironmentFiles.some(file => existsSync(file))
  ) throw new Error('Hosted builds require the guarded build command and a clean environment.');

  if (!resolveHostedConfig({
    deployment,
    authMode: process.env.NEXT_PUBLIC_AUTH_MODE,
    localDemo: process.env.NEXT_PUBLIC_LOCAL_DEMO,
    apiUrl: process.env.NEXT_PUBLIC_API_URL,
    frontendOrigin: process.env.NEXT_PUBLIC_FRONTEND_ORIGIN,
    supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL,
    supabasePublishableKey: process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
  })) throw new Error('Hosted frontend configuration is invalid.');
}

const nextConfig: NextConfig = {
  output: 'export', images: { unoptimized: true }, agentRules: false,
  ...(deployment === 'hosted'
    ? {distDir: 'out-hosted'}
    : process.env.INTRASPOT_FRONTEND_PROFILE === 'real' ? {distDir: 'out-real'} : {}),
};

export default nextConfig;
