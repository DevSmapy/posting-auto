import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';
import { isPublicHttpUrl } from './lib/urls';

const posts = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/posts' }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    published_at: z.coerce.date(),
    category: z.string(),
    tags: z.array(z.string()).default([]),
    cover: z.string().optional(),
    graphic: z.string().optional(),
    kind: z.enum(['briefing', 'note']).default('briefing'),
    sources: z
      .array(
        z.object({
          title: z.string(),
          url: z
            .string()
            .optional()
            .refine((value) => value == null || isPublicHttpUrl(value), {
              message: 'source url must be http or https',
            }),
        }),
      )
      .default([]),
    status: z.enum(['published', 'draft']).default('published'),
  }),
});

export const collections = { posts };
