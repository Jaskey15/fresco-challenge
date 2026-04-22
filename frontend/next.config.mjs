/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack: (config) => {
    // Required by pdfjs-dist when used via react-pdf
    config.resolve.alias.canvas = false;
    return config;
  },
};
export default nextConfig;
