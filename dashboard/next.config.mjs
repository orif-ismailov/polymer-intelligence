/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Output as standalone for Docker deployment
  output: "standalone",
};

export default nextConfig;
