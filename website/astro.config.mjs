// @ts-check
import sitemap from '@astrojs/sitemap';
import { defineConfig } from 'astro/config';

const configured = (process.env.SITE_BASE_URL || '').trim().replace(/\/$/, '');
const isBuild = process.argv.includes('build');

if (isBuild && !configured) {
  throw new Error(
    'SITE_BASE_URL is required for production builds. Set a real origin, for example https://example.com',
  );
}

const site = configured || 'https://briefing.example';

export default defineConfig({
  site,
  integrations: [sitemap()],
});
