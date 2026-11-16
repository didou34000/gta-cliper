import type { NextConfig } from "next";

// Pages démo à filmer (/flex, /board) : fichiers statiques dans public/.
const config: NextConfig = {
  async rewrites() {
    return [
      { source: "/flex", destination: "/flex.html" },
      { source: "/board", destination: "/board.html" },
    ];
  },
};

export default config;
