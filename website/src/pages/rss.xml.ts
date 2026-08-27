import type { APIRoute } from 'astro';
import { publishedPosts, postPath } from '../lib/posts';

export const GET: APIRoute = async ({ site }) => {
  const origin = (site ?? new URL('https://briefing.example')).toString().replace(/\/$/, '');
  const posts = await publishedPosts();
  const items = posts
    .map((post) => {
      const link = `${origin}${postPath(post)}`;
      return `  <item>
    <title>${escapeXml(post.data.title)}</title>
    <link>${link}</link>
    <guid>${link}</guid>
    <pubDate>${post.data.published_at.toUTCString()}</pubDate>
    <description>${escapeXml(post.data.description)}</description>
  </item>`;
    })
    .join('\n');

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>장전 브리핑</title>
    <link>${origin}/</link>
    <description>한국 경제와 시사. 매일 아침, 오늘 무엇이 중요한지.</description>
    <language>ko</language>
${items}
  </channel>
</rss>
`;
  return new Response(xml, {
    headers: { 'Content-Type': 'application/rss+xml; charset=utf-8' },
  });
};

function escapeXml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}
