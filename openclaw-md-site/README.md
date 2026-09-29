# OpenClaw Markdown Site

A dependency-free Python static-site generator with a hardened Docker Compose deployment for a deliberately selected set of Markdown documents. It is intended for local or authenticated private-network reading of sensitive VA and medical material—not for publishing a workspace.

> **Privacy warning:** VA and medical documents may contain PII/PHI. Do not expose this service publicly without authenticated private ingress. `robots.txt`, `noindex`, loopback binding, and unguessable URLs are not authentication. Read [PRIVACY.md](PRIVACY.md) before hosting.

## Docker architecture and publication boundary

The image uses two stages:

1. A Python Alpine builder copies only `mdsite.py`, `site.docker.json`, and `content/`. It runs the standard-library-only generator at image build time.
2. An nginx Alpine runtime receives only generated static output from the builder. It runs as UID/GID `101:101`; the final image does **not** contain source Markdown, Python, `mdsite.py`, or `site.docker.json`.

`.dockerignore` denies the whole tool directory and narrowly re-allows only the files needed by those stages. There are no runtime volumes, analytics, CDNs, external fonts, or network dependencies. `content/` is the explicit publication boundary: a file must be copied there **and** named in the exact `site.docker.json` allowlist before it can be rendered.

The included IBS Markdown is an approved example copied from the current workspace output. Its original file is not changed.

## Docker Compose quick start

Requirements: Docker Engine/Desktop with Compose v2. Run all commands from this directory.

### 1. Copy only approved Markdown

Review and redact each source first. For the current approved example:

```sh
cp ../../output/2026-09-25-IBS-gastroenterology-appointment-prep.md content/
```

Do not point Docker at a workspace, `records/`, or `output/` directory. Do not add a volume mount for those locations.

### 2. Edit the exact allowlist

Edit `site.docker.json`. Keep `sources[].root` set to `content` and list every approved file by exact name:

```json
{
  "root": "content",
  "include": [
    "2026-09-25-IBS-gastroenterology-appointment-prep.md"
  ],
  "exclude": []
}
```

Prefer exact filenames. A narrow subdirectory glob is acceptable only when every matching Markdown file is approved. The generator ignores non-Markdown files and denies hidden, `records`, `memory`, private, secret, and similar paths even if a broad glob is added.

### 3. Validate, build, and start

```sh
docker compose config
docker compose build
docker compose up -d
```

Equivalently, the final two commands may be combined after content/config review:

```sh
docker compose up --build -d
```

Expected local URL: <http://127.0.0.1:8080/>  
Expected IBS page: <http://127.0.0.1:8080/docs/2026-09-25-ibs-gastroenterology-appointment-prep.html>

The default publish address is loopback only:

```text
127.0.0.1:8080 -> container port 8080
```

### Health, logs, and stop

```sh
docker compose ps
docker compose exec site wget -q -O - http://127.0.0.1:8080/healthz
docker compose logs --tail=100 site
docker compose down
```

`docker compose ps` should report `healthy`. `docker compose down` removes the test/runtime container and network; the locally built image remains until deliberately removed.

### Update content or configuration

The generator runs while the image is built, not when the container starts. **Every Markdown or `site.docker.json` change requires an image rebuild.** After reviewing the changed source and allowlist:

```sh
docker compose config
docker compose up --build -d
docker compose ps
```

There is intentionally no live content mount. This prevents accidental publication of newly created workspace files.

## Bind address and port

Copy the non-secret example and edit concrete values if needed:

```sh
cp .env.example .env
```

Local-only default:

```dotenv
BIND_ADDRESS=127.0.0.1
PORT=8080
```

To bind only to a private LAN address, use that host address, for example:

```dotenv
BIND_ADDRESS=192.168.1.25
PORT=8080
```

To bind only to this host's Tailscale address, find it and place the concrete address in `.env`:

```sh
tailscale ip -4
```

```dotenv
BIND_ADDRESS=100.x.y.z
PORT=8080
```

Then validate and recreate:

```sh
docker compose config
docker compose up -d --force-recreate
```

Expected URL becomes `http://<BIND_ADDRESS>:<PORT>/`. Avoid `0.0.0.0`: it listens on every host interface. LAN or Tailscale reachability narrows exposure but does not by itself provide application authentication. Firewall and Tailscale ACLs/grants still need review.

## Reverse proxy and authentication

For access beyond the local machine, the recommended design is:

1. Keep this Compose service on `127.0.0.1`.
2. Put an operator-managed HTTPS reverse proxy or private ingress in front of it.
3. Require tested identity-aware authentication and authorization (for example a restrictive Tailscale ACL policy, an SSO access proxy, mutual TLS, or another reviewed access gateway).
4. Verify access in a logged-out/unauthorized client and review proxy, artifact, cache, and access-log retention.

The bundled nginx is deliberately only a static server; it does not claim to provide user authentication. Do not expose VA/medical documents on a public IP, public DNS endpoint, public bucket, Pages site, or unauthenticated tunnel. TLS alone encrypts transport; it does not decide who may read the documents.

## Security defaults

The Compose service uses:

- loopback-only host publishing by default;
- a non-root nginx process (`101:101`) on container port 8080;
- a read-only root filesystem and small `noexec,nosuid,nodev` `/tmp` tmpfs;
- all Linux capabilities dropped and `no-new-privileges`;
- a process limit, healthcheck, graceful stop, and `unless-stopped` restart policy;
- no host volumes, secrets, cookies, forms, analytics, CDNs, or runtime outbound requests;
- CSP, clickjacking, MIME-sniffing, referrer, permissions, and cross-origin headers;
- `Cache-Control: private, no-store` for all responses;
- dotfile denial, disabled directory listing, `robots.txt`, and page-level `noindex` metadata.

These are defense in depth, not a substitute for access control.

## Backups, registries, and non-secret configuration

`compose.yaml`, `Dockerfile`, `nginx.conf`, `.env.example`, and the sample settings are ordinary non-secret infrastructure. `.env` contains only bind settings by default and is git-ignored.

Treat all of the following as sensitive when the source contains PII/PHI:

- files in `content/`;
- generated `dist/` or other site output;
- the built image, exported image tarballs, registry copies, Docker build cache, and host backups;
- `search-index.json`, which contains searchable document text;
- logs or screenshots that reveal document paths/content.

`content/**`, `dist/`, and `build/` are git-ignored while `content/.gitkeep` remains trackable. Do not force-add sensitive files to Git. Use encrypted, access-controlled backups with tested deletion/retention, and do not push the image to a public registry. Removing a container does not remove image layers, build cache, registry copies, or backups.

## Native generator use

Python 3.10+ is supported with no third-party packages:

```sh
python3 mdsite.py build --config site.json --clean
python3 mdsite.py serve --config site.json --host 127.0.0.1 --port 8000
```

The native `site.json` remains separate from Docker's publication-boundary config. Its current output is `../../output/openclaw-docs-site`.

### Generator safety behavior

- `--config` is required; there is no implicit whole-workspace source.
- Every source requires a non-empty `include` list.
- Only matching `.md` files are read; PDFs/images/assets are not copied.
- Hidden and common sensitive paths are denied in code.
- Raw HTML is escaped and unsafe links are disabled.
- Non-empty output requires `--clean`, which only removes a directory bearing this generator's safety marker.
- Generated citations show filenames, never configured absolute filesystem paths.

See [PRIVACY.md](PRIVACY.md) for the full threat model. This intentionally small renderer supports headings, prose, lists/tasks, blockquotes, tables, fenced/inline code, safe links, print styling, navigation, and in-browser search. It is not full CommonMark and does not copy images or arbitrary HTML.

## Tests and validation

Run the unit and packaging checks:

```sh
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

Validate the Compose model before deployment:

```sh
docker compose config
```

A full release check should build/start the image, wait for `healthy`, request `/`, the allowlisted document, `/robots.txt`, and `/search-index.json`, verify response headers, confirm the container runs as `101:101`, inspect the final filesystem for absence of Markdown/Python/builder files, test a restart, and finish with `docker compose down`.

## CLI help

```sh
python3 mdsite.py --help
python3 mdsite.py build --help
python3 mdsite.py serve --help
```
