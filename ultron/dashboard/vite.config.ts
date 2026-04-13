import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3456,
    proxy: {
      '/dashboard/overview': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/dashboard/memories': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/dashboard/skills': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/dashboard/leaderboard': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/dashboard/agent-skill-package': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/memory': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/auth': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/harness/': { target: 'http://127.0.0.1:8001', changeOrigin: true },
      '/i/': { target: 'http://127.0.0.1:8001', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
