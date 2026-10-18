import { getCollection } from "astro:content";

/** Prefix a site-relative path with the deploy base ("/" locally, "/hayate/" on Pages). */
export function url(path = ""): string {
  const base = import.meta.env.BASE_URL.replace(/\/?$/, "/");
  return base + path.replace(/^\//, "");
}

/** Published posts, newest first; posts on the same date go by weekend, highest first. Drafts show up in `npm run dev` only. */
export async function getPosts() {
  const posts = await getCollection("blog", ({ data }) => import.meta.env.DEV || !data.draft);
  return posts.sort(
    (a, b) =>
      b.data.pubDate.valueOf() - a.data.pubDate.valueOf() || (b.data.weekend ?? -1) - (a.data.weekend ?? -1),
  );
}

export function formatDate(date: Date): string {
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
