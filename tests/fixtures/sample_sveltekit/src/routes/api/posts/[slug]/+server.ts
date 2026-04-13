import { json } from '@sveltejs/kit';

interface Post {
  slug: string;
  title: string;
  body: string;
}

/**
 * Fetch or update a single post.
 */
export async function GET({ params, url }) {
  const expand = url.searchParams.get('expand');
  const post: Post = {
    slug: params.slug,
    title: expand ? 'Expanded title' : 'Short title',
    body: 'Stored content',
  };
  return json(post);
}

export const PATCH = async ({ request, params }) => {
  const body = await request.json();
  return json({
    slug: params.slug,
    title: body.title,
    body: body.body,
  });
};
