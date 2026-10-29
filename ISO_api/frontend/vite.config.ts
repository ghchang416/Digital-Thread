import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'ISO_');
  return {
    plugins: [react()],
    server: {
      port: 8080, strictPort: true,
      proxy: { '/api': { target: process.env.ISO_API_PROXY_TARGET || env.ISO_API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: true } },
    },
  };
});
