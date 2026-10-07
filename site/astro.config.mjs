// @ts-check
import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

// In CI, actions/configure-pages provides the origin and base path
// (e.g. https://<user>.github.io and /hayate), so nothing is hard-coded.
export default defineConfig({
  site: process.env.SITE_URL || "http://localhost:4321",
  base: process.env.BASE_PATH || "/",
  trailingSlash: "always",
  integrations: [sitemap()],
});
