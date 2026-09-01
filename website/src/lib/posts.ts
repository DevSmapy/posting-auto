import { getCollection, type CollectionEntry } from 'astro:content';

export type Post = CollectionEntry<'posts'>;

export function postPath(post: Post): string {
  return `/articles/${post.id}`;
}

export function postVisual(post: Post): { src: string; kind: 'cover' | 'graphic' } | undefined {
  if (post.data.graphic) {
    return { src: post.data.graphic, kind: 'graphic' };
  }
  if (post.data.cover) {
    return { src: post.data.cover, kind: 'cover' };
  }
  return undefined;
}

export function postKicker(post: Post): string {
  const base = `${post.data.category} · ${formatDate(post.data.published_at)}`;
  if (post.data.kind === 'note') {
    return `${base} · 단신`;
  }
  return base;
}

export function formatDate(value: Date): string {
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(value);
}

export async function publishedPosts(): Promise<Post[]> {
  const posts = await getCollection('posts', ({ data }) => data.status === 'published');
  return posts.sort((a, b) => b.data.published_at.getTime() - a.data.published_at.getTime());
}

export function categoriesOf(posts: Post[]): string[] {
  return [...new Set(posts.map((post) => post.data.category))];
}
