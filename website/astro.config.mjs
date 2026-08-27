// @ts-check
import sitemap from '@astrojs/sitemap';
import { defineConfig } from 'astro/config';

const site = (process.env.SITE_BASE_URL || 'https://briefing.example').replace(/\/$/, '');

export default defineConfig({
  site,
  integrations: [sitemap()],
});
