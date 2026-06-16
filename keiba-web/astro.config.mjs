// @ts-check
import { defineConfig } from 'astro/config';
import preact from '@astrojs/preact';

// GitHub Pages: https://wattakoumei.github.io/keiba/
// 同一リポ keiba/ のサブディレクトリ。report.json は ../data から build 時に直読み。
export default defineConfig({
  site: 'https://wattakoumei.github.io',
  base: '/keiba/',
  integrations: [preact()],
});
