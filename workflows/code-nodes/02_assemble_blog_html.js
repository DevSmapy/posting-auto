/**
 * n8n Code 노드 샘플: 브리핑 JSON → 티스토리 HTML 조립
 * 입력: $json = Ollama briefing object
 */
const b = items[0].json;
const esc = (s = '') =>
  String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

const parts = [];
parts.push(`<p>${esc(b.intro || '')}</p>`);
parts.push(`<p><strong>오늘 한줄</strong> ${esc(b.market_one_liner || '')}</p>`);
for (const story of b.stories || []) {
  parts.push(`<h2>${esc(story.headline || '')}</h2>`);
  parts.push(`<p>${esc(story.summary || '')}</p>`);
  parts.push(`<p><em>${esc(story.why_it_matters || '')}</em></p>`);
  parts.push(
    `<p>출처: <a href="${esc(story.source_url || '#')}">${esc(story.source_name || '')}</a></p>`,
  );
}
parts.push('<h2>오늘 포인트</h2><ul>');
for (const p of b.today_points || []) parts.push(`<li>${esc(p)}</li>`);
parts.push('</ul><hr>');
parts.push(
  '<p>본 콘텐츠는 정보 안내용이며 특정 종목의 매수·매도·투자를 권유하지 않습니다. 투자 판단과 책임은 독자 본인에게 있습니다.</p>',
);

return [
  {
    json: {
      ...b,
      blog_html: parts.join('\n'),
      tag_csv: (b.blog_tags || []).join(','),
    },
  },
];
