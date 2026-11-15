# aitiolin.io website

Static source of [aitiolin.io](https://aitiolin.io). There is no build step: the files below are
uploaded to the web root as they are. Open `index.html` in a browser to preview.

## Published files

| File | Purpose |
|------|---------|
| `index.html` | Landing page |
| `methods.html` | Methods and limitations guide for Reviewed comparison |
| `impressum.html`, `privacy.html`, `disclaimer.html` | Legal pages (German). Impressum and privacy carry `noindex` so search engines do not list the postal address. |

`impressum.html` and `privacy.html` contain a postal address, so they are git-ignored and exist only in
local copies of this folder. Back them up outside the repository; a fresh clone does not have them, and
the site's footer links to them.
| `aitiol.png`, `canvas.PNG`, `copilot.PNG`, `identification.PNG`, `sensitivity.PNG` | Screenshots used on the landing page. The file names are case-sensitive on the server. |
| `favicon.ico`, `favicon.svg`, `apple-touch-icon.png` | Browser and home-screen icons, drawn from the header's brand mark |
| `og-image.png` | 1200×630 preview image for links shared on social media and in chats |
| `robots.txt`, `sitemap.xml` | Crawler instructions and the list of indexable pages. Update `lastmod` in the sitemap when a listed page changes. |

## Not published

- `methods-reference.html` - the detailed technical reference for Reviewed comparison (estimators,
  interval methods, limits and references), linked from the app README. It is kept with the site
  source because it shares the subject of `methods.html`, but it is not linked from the site.
- `README.md` - this file.

## Checks

CI scans the `.html` files here for claims the prototype must not make (see
`.github/workflows/aitiolin-ci.yml`). Keep the "Source version" on the landing page in line with
`../VERSION` when a release is published.
