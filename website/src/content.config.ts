import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const posts = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/posts' }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    published_at: z.coerce.date(),
    category: z.string(),
    tags: z.array(z.string()).default([]),
    cover: z.string().optional(),
    sources: z
      .array(
        z.object({
          title: z.string(),
          url: z.string().optional(),
        }),
      )
      .default([]),
    status: z.enum(['published', 'draft']).default('published'),
  }),
});

export const collections = { posts };
