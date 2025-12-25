## Purpose

This file gives AI coding agents the minimal, high-value context to be productive in this Homelab / MediaStack repository. It focuses on the "big picture", developer workflows, repo-specific patterns, and exact files to inspect when making changes.

## Big picture (what this repo is)
- Homelab: a collection of Docker service definitions and helper scripts to run a self-hosted media stack.
- MediaStack is the main subproject: a Docker-based media server ecosystem (Jellyfin, Plex, *ARR apps, Traefik, Authentik, Gluetun VPN, etc.). See `mediastack/README.md` for an overview and architecture diagrams.
- Key runtime model: services are defined with Docker Compose variants under `mediastack/` (three flavours: `full-download-vpn`, `mini-download-vpn`, `no-download-vpn`).

## Most important files & directories
- `mediastack/base-working-files/.env` — canonical environment variables (PUID/PGID, paths, ports, VPN and Cloudflare settings). Always inspect this first; it drives compose templates.
- `mediastack/full-download-vpn/docker-compose.yaml` — full-stack compose with Gluetun as the VPN gateway (most services route through it). Use this to understand service labels/networks.
- `mediastack/mini-download-vpn/docker-compose.yaml` and `mediastack/no-download-vpn/docker-compose.yaml` — alternate networking choices.
- `mediastack/README.md` — architecture details, diagrams, and usage notes (VPN vs non-VPN, Traefik integration).
- `Caddy/Caddyfile` and `Docker/**/compose.yaml` — other services and reverse-proxy examples in the repo.
- Top-level `readme.md` — host-level notes and troubleshooting tips (Docker restart, mounts).

## Key conventions & patterns (repo-specific)
- Single env-driven model: compose files reference variables from `mediastack/base-working-files/.env` (e.g., `${DOCKER_SUBNET}`, `${PUID}`, `${FOLDER_FOR_DATA}`). Keep `.env` synchronized with the compose variant you run.
- Network pattern: compose creates a named `mediastack` Docker bridge network (subnet configured from `DOCKER_SUBNET` / `DOCKER_GATEWAY`). Many services attach to this network explicitly.
- VPN routing: the Gluetun container is used as a network gateway. In the `full-download-vpn` composer all (or most) containers are attached to the Gluetun-protected network; in other variants only download services may be routed.
- Reverse-proxy labels: Traefik routing is configured via Docker labels in the compose files. Labels use `CLOUDFLARE_DNS_ZONE` and host rules like `Host(`auth.${CLOUDFLARE_DNS_ZONE})`. When editing services, update or preserve these labels.
- Runtime user mapping: containers run with `user: ${PUID}:${PGID}` — host file ownership is important. Expect PUID/PGID mapping in `.env`.

## Developer workflows (concrete commands)
- Prepare env (run from repo root or a working dir that will run compose):
  ```bash
  cp mediastack/base-working-files/.env ./
  # edit .env to set FOLDER_FOR_MEDIA, FOLDER_FOR_DATA, PUID, PGID, and secrets
  ```
- Start full stack (example):
  ```bash
  docker compose --env-file . -f mediastack/full-download-vpn/docker-compose.yaml up -d
  ```
- Bring stack down:
  ```bash
  docker compose --env-file . -f mediastack/full-download-vpn/docker-compose.yaml down
  ```
- Check logs / debugging:
  ```bash
  docker compose -f mediastack/full-download-vpn/docker-compose.yaml logs -f authentik
  docker ps --filter name=mediastack
  docker network inspect mediastack
  docker logs -f <container>
  ```
- Traefik dashboard: default port is set by `WEBUI_PORT_TRAEFIK` in `.env` (commonly `8080`). Visit `http://<DOCKER-IP>:${WEBUI_PORT_TRAEFIK}` to view router/service status.

## Integration points & external dependencies to watch for
- Traefik + Cloudflare: many services depend on `CLOUDFLARE_DNS_ZONE` and `CLOUDFLARE_DNS_API_TOKEN` for certificate automation and domain routing.
- Authentik (SSO) and Headscale/Tailscale: Authentik requires PostgreSQL and Valkey (Redis-like) configured in compose; Headscale/Tailscale require an auth key in `.env`.
- Gluetun VPN: requires provider credentials and correct `VPN_TYPE` settings in `.env`. If Gluetun stops, dependent containers may lose outgoing connectivity.
- Persistent storage: compose mounts host folders under `FOLDER_FOR_DATA` and `FOLDER_FOR_MEDIA` — ensure these exist and match `PUID/PGID`.

## Editing and testing advice (do this first)
- Always read `mediastack/base-working-files/.env` before editing compose files — many variables are inlined there.
- Don't commit real secrets. The repo contains an example `.env` with keys/tokens — replace with local secrets and add to `.gitignore` if you store working `.env` in the repo root.
- When adding or changing Traefik labels, mirror an existing service label block (see `guacamole` in `full-download-vpn/docker-compose.yaml`) to ensure routers, services and middlewares are consistent.
- If you change container ports, update the matching `WEBUI_PORT_*` variables in `.env` so the compose files bind correctly.

## Quick file examples to inspect when making changes
- Read these when you need concrete examples: 
  - `mediastack/base-working-files/.env` (env variable mapping)
  - `mediastack/full-download-vpn/docker-compose.yaml` (service labels, networks, healthchecks)
  - `mediastack/mini-download-vpn/docker-compose.yaml` (alternate network choices)
  - `Caddy/Caddyfile` (reverse-proxy example)

## What to ask the user if unclear
- Which compose variant should CI/automation target (full/mini/no-download)?
- Which services are considered "managed" vs "experimental" (i.e., safe to change labels or network settings)?
- Are there private secrets that should be vaulted outside the repo (Cloudflare/API, VPN credentials)?

Please review this draft and tell me which areas you want expanded (examples, common edits, or CI deployment instructions). I can iterate with more targeted instructions or add examples for common change types (add service, change Traefik route, move service to VPN network).
