/**
 * n8n Code 노드 샘플: 브리핑 JSON → 티스토리 HTML 조립 (v2)
 * 입력: $json = Ollama briefing object
 */
const b = items[0].json;
const esc = (s = '') =>
  String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

const coreSummary = () => {
  if (b.core_summary?.length) return b.core_summary.map(String);
  if (b.today_points?.length) return b.today_points.map(String);
  if (b.market_one_liner) return [String(b.market_one_liner)];
  return [];
};

const whatHappened = (story) =>
  String(story.what_happened || story.summary || '').trim();
const whyImportant = (story) =>
  String(story.why_important || story.why_it_matters || '').trim();
const safeSourceUrl = (value) => {
  const url = String(value || '').trim();
  return /^https?:\/\//i.test(url) ? url : '#';
};

const parts = [];
const intro = String(b.intro || '').trim();
if (intro) {
  parts.push(`<p>${esc(intro)}</p>`);
  parts.push('<hr>');
}

const summary = coreSummary();
if (summary.length) {
  parts.push('<h2>📌 오늘의 핵심 요약</h2><ul>');
  for (const point of summary) parts.push(`<li>${esc(point)}</li>`);
  parts.push('</ul><hr>');
}

for (let i = 0; i < (b.stories || []).length; i++) {
  const story = b.stories[i];
  const headline = String(story.headline || '').trim();
  parts.push(`<h2>${i + 1}. ${esc(headline)}</h2>`);
  const what = whatHappened(story);
  if (what) {
    parts.push('<h3>무슨 일이 있었나?</h3>');
    parts.push(`<p>${esc(what)}</p>`);
  }
  const why = whyImportant(story);
  if (why) {
    parts.push('<h3>왜 중요한가?</h3>');
    parts.push(`<p>${esc(why)}</p>`);
  }
  const watch = String(story.watch_next || '').trim();
  if (watch) {
    parts.push('<h3>앞으로 주목할 점</h3>');
    parts.push(`<p>${esc(watch)}</p>`);
  }
  const one = String(story.one_liner || '').trim();
  if (one) {
    parts.push('<h3>한 줄 요약</h3>');
    parts.push(`<p>${esc(one)}</p>`);
  }
  if (story.source_url || story.source_name) {
    parts.push(
      `<p>출처: <a href="${esc(safeSourceUrl(story.source_url))}">${esc(story.source_name || '링크')}</a></p>`,
    );
  }
  parts.push('<hr>');
}

const impact = b.market_impact || {};
const pos = impact.positive || [];
const neu = impact.neutral || [];
const neg = impact.negative || [];
if (pos.length || neu.length || neg.length) {
  parts.push('<h2>📈 오늘의 시장·산업 영향</h2>');
  if (pos.length) {
    parts.push('<p><strong>긍정적인 영향</strong></p><ul>');
    for (const item of pos) parts.push(`<li>${esc(item)}</li>`);
    parts.push('</ul>');
  }
  if (neu.length) {
    parts.push('<p><strong>중립적인 영향</strong></p><ul>');
    for (const item of neu) parts.push(`<li>${esc(item)}</li>`);
    parts.push('</ul>');
  }
  if (neg.length) {
    parts.push('<p><strong>부정적인 영향</strong></p><ul>');
    for (const item of neg) parts.push(`<li>${esc(item)}</li>`);
    parts.push('</ul>');
  }
}

const insight = String(b.insight || '').trim();
if (insight) {
  parts.push('<h2>🔍 오늘의 인사이트</h2>');
  parts.push(`<p>${esc(insight)}</p>`);
}

const events = b.upcoming_events || [];
if (events.length) {
  parts.push('<h2>📅 앞으로 주목할 일정</h2><ul>');
  for (const ev of events) {
    if (typeof ev !== 'object' || ev === null) {
      parts.push(`<li>${esc(ev)}</li>`);
      continue;
    }
    const date = String(ev.date || '').trim();
    const title = String(ev.title || '').trim();
    const desc = String(ev.description || '').trim();
    let label = [date, title].filter(Boolean).join(' — ') || title;
    if (desc) label = label ? `${label}: ${desc}` : desc;
    parts.push(`<li>${esc(label)}</li>`);
  }
  parts.push('</ul>');
}

const closing = String(b.closing_remark || '').trim();
if (closing) {
  parts.push('<h2>✨ 오늘의 한마디</h2>');
  parts.push(`<p>${esc(closing)}</p>`);
}

parts.push('<hr>');
const keywords = b.related_keywords || [];
if (keywords.length) {
  parts.push('<h3>관련 키워드</h3>');
  parts.push(`<p>${esc(keywords.join(', '))}</p>`);
}
parts.push(
  '<p>※ 본 글은 정보 제공을 목적으로 작성되었으며 투자 또는 의사결정을 위한 전문적인 조언이 아닙니다.</p>',
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
