/**
 * n8n Code 노드 샘플: RSS 아이템 배열을 merge한 뒤
 * 당일 필터 + cluster_size + feed_rank 부여.
 *
 * 입력 가정: items[].json 에 title, link, content/summary, pubDate, topic 존재
 */
const TZ = 'Asia/Seoul';
const max = Number($env.NEWS_MAX_CANDIDATES || 20);

function stripHtml(s = '') {
  return s.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

function clusterSize(html = '') {
  return (html.match(/<li\b/gi) || []).length;
}

function isToday(pubDate) {
  if (!pubDate) return true;
  const d = new Date(pubDate);
  const local = new Date(d.toLocaleString('en-US', { timeZone: TZ }));
  const now = new Date(new Date().toLocaleString('en-US', { timeZone: TZ }));
  return local.toDateString() === now.toDateString();
}

const rows = items
  .map((item, idx) => {
    const j = item.json;
    const desc = j.content || j.summary || j.description || '';
    return {
      id: j.link || String(idx),
      title: stripHtml(j.title || ''),
      snippet: stripHtml(desc).slice(0, 800),
      link: j.link || '',
      source: j.source || '',
      published_at: j.pubDate || j.isoDate || null,
      topic: j.topic || 'BUSINESS',
      feed_rank: j.feed_rank || idx + 1,
      cluster_size: clusterSize(desc),
    };
  })
  .filter((r) => r.title && r.title !== 'Google 뉴스')
  .filter((r) => isToday(r.published_at));

const seen = new Set();
const unique = [];
for (const r of rows) {
  const key = (r.title || '').replace(/\s+/g, '').toLowerCase();
  if (seen.has(key)) continue;
  seen.add(key);
  unique.push(r);
}

unique.sort((a, b) => {
  const ta = a.topic === 'BUSINESS' ? 0 : 1;
  const tb = b.topic === 'BUSINESS' ? 0 : 1;
  if (ta !== tb) return ta - tb;
  if (a.feed_rank !== b.feed_rank) return a.feed_rank - b.feed_rank;
  return b.cluster_size - a.cluster_size;
});

return unique.slice(0, max).map((json) => ({ json }));
