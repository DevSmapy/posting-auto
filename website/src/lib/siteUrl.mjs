/**
 * Canonical site origin for Astro (`site`) and sitemap/OG URLs.
 * Prefer an explicit SITE_BASE_URL; on Vercel, use the platform host.
 */
export function resolveSiteUrl(env = process.env, argv = process.argv) {
  const explicit = (env.SITE_BASE_URL || '').trim().replace(/\/$/, '');
  if (explicit) return explicit;

  const vercelHost = (env.VERCEL_PROJECT_PRODUCTION_URL || env.VERCEL_URL || '')
    .trim()
    .replace(/^https?:\/\//, '')
    .replace(/\/$/, '');
  if (vercelHost) return `https://${vercelHost}`;

  if (argv.includes('build')) {
    throw new Error(
      'SITE_BASE_URL is required for production builds. Set a real origin, for example https://example.com',
    );
  }
  return 'https://briefing.example';
}
