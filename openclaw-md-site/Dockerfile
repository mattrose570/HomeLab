# syntax=docker/dockerfile:1.7

FROM python:3.13-alpine AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /build

# Intentionally explicit: the builder receives only the generator, Docker config,
# and files deliberately placed behind the content/ publication boundary.
COPY mdsite.py site.docker.json ./
COPY content/ ./content/
RUN python3 mdsite.py build --config site.docker.json \
    && find /build/dist -type d -exec chmod 0555 {} + \
    && find /build/dist -type f -exec chmod 0444 {} +

FROM nginx:1.29-alpine AS runtime

LABEL org.opencontainers.image.title="OpenClaw Markdown Site" \
      org.opencontainers.image.description="Private, dependency-free static document library"

RUN rm -rf /usr/share/nginx/html/* /etc/nginx/conf.d/* /docker-entrypoint.d/*
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=builder --chown=101:101 /build/dist/ /usr/share/nginx/html/

USER 101:101
EXPOSE 8080
STOPSIGNAL SIGQUIT
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
ENTRYPOINT ["nginx", "-c", "/etc/nginx/nginx.conf", "-g", "daemon off;"]
