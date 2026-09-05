// @ts-check
import sitemap from '@astrojs/sitemap';
import { defineConfig } from 'astro/config';
import { resolveSiteUrl } from './src/lib/siteUrl.mjs';

export default defineConfig({
  site: resolveSiteUrl(),
  integrations: [sitemap()],
});
