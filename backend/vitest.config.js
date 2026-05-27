import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'static') },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/js/**/*.test.js'],
  },
});
