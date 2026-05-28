// Cursor: Next.js config for apps/frontend (strict + image domains)
import { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  experimental: {
    appDir: true
  },
  images: {
    // Cloudflare R2 signed URL host (placeholder)
    domains: ["r2.cloudflarestorage.com", "static.example.com"]
  }
};

export default config;
