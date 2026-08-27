import { getCollection, type CollectionEntry } from 'astro:content';

export type Post = CollectionEntry<'posts'>;

export function postPath(post: Post): string {
  return `/articles/${post.id}`;
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
