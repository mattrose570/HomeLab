# Privacy and threat model

VA claims and medical documents can contain **PII, PHI, service history, claim strategy, and other sensitive facts**. This generator therefore publishes nothing implicitly: every Markdown file must match an `include` entry in the selected JSON config.

## Safe defaults

- Markdown only; files and assets are not copied automatically.
- Each source block requires an explicit, non-empty `include` allowlist.
- Hidden paths, `memory`, `records`, source-PDF directories, private/secrets directories, `.git`, and similar paths are excluded by code even if a broad include matches them.
- Raw HTML is escaped. Link schemes are limited; unsafe links are disabled.
- Generated pages contain no analytics, cookies, external fonts, CDNs, forms, remote embeds, or automatic network calls.
- A restrictive Content Security Policy blocks outbound page requests.
- Generated pages use `noindex` metadata and `robots.txt` contains `Disallow: /`.
- Generated citations show only the source filename, never an absolute local path.

## What these controls do not do

A static site is readable by anyone who can reach it. **`robots.txt`, no-index metadata, obscure URLs, and a Content Security Policy are not authentication or access control.** They cannot keep a public bucket, Pages project, or web server private.

Prefer local use. If hosting is necessary, use a private network or a platform with tested identity-aware authentication and authorization. Verify cache, preview-deployment, artifact, log, and sharing settings. Do not place the output in a public Git repository. Remove a deployment from the host as well as from DNS; assume any previously public content may have been copied.

Before every build and deployment:

1. Review every `sources[].root` and `sources[].include` entry.
2. Inspect `search-index.json`; it intentionally contains searchable document text.
3. Inspect the generated pages and confirm only intended files appear.
4. Confirm the hosting destination is private and access-tested in a logged-out browser.

The generator reduces accidental publication. It cannot make a public static host confidential.
