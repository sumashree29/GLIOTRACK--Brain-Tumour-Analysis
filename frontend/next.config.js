/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // All API calls go directly to NEXT_PUBLIC_API_BASE (Render backend).
  // No Next.js API route proxy needed — Render handles CORS headers.

  // Allow images from Supabase Storage (report PDFs served as previews)
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "*.supabase.co",
      },
      {
        protocol: "https",
        hostname: "*.supabase.in",
      },
    ],
  },

  // Silence noisy peer-dependency warnings from recharts / date-fns
  experimental: {
    optimizePackageImports: ["lucide-react", "recharts", "date-fns"],
  },
};

module.exports = nextConfig;
