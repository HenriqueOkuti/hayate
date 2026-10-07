import rss from "@astrojs/rss";
import type { APIContext } from "astro";
import { getPosts, url } from "../lib";

export async function GET(context: APIContext) {
  const posts = await getPosts();
  return rss({
    title: "Hayate 疾風",
    description: "Progress notes from Hayate, a sub-millisecond web-page categorizer distilled from an LLM.",
    site: new URL(url(), context.site ?? "http://localhost:4321").href,
    items: posts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.pubDate,
      link: url(`posts/${post.id}/`),
    })),
  });
}
