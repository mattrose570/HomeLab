#!/bin/bash

# Install Docker Engine, Buildx and Compose on Debian or Ubuntu.
# Usage: sudo bash /path/to/dockerSetup.sh [docker-user]
# User selection: argument, then TRUENAS_USERNAME in the optional sibling .env,
# then SUDO_USER. Docker group membership grants root-equivalent access.
set -Eeuo pipefail
trap 'printf "Docker setup failed at line %s. See the error above.\n" "$LINENO" >&2' ERR

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=utils/utils.sh
source "$SCRIPT_DIR/utils/utils.sh"
root_check
[[ $# -le 1 ]] || fail "Usage: sudo bash $0 [docker-user]"
REQUESTED_USER="${1:-}"

# The shared loader resolves .env relative to the working directory.
cd -- "$SCRIPT_DIR"
if [[ -f .env ]]; then
  # Preserve the existing .env convention: unset optional variables expand empty.
  set +u
  load_env_variables
  set -u
fi
DOCKER_USER="${REQUESTED_USER:-${TRUENAS_USERNAME:-${SUDO_USER:-}}}"
[[ -n "$DOCKER_USER" ]] || fail "Pass a login username, or set TRUENAS_USERNAME in .env."
USER_ID="$(id -u -- "$DOCKER_USER")" || fail "User '$DOCKER_USER' does not exist."
[[ "$USER_ID" != 0 ]] || fail "Choose a non-root login user for the docker group."

[[ -r /etc/os-release ]] || fail "This script requires Debian or Ubuntu."
# shellcheck source=/dev/null
source /etc/os-release
DISTRO="${ID:-}"
case "$DISTRO" in
  debian) CODENAME="${VERSION_CODENAME:-}" ;;
  ubuntu) CODENAME="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}" ;;
  *) fail "Unsupported distribution '$DISTRO'; expected Debian or Ubuntu." ;;
esac
[[ "$CODENAME" =~ ^[a-z0-9][a-z0-9._-]*$ ]] || fail "Missing or invalid OS release codename."
ARCH="$(dpkg --print-architecture)"
[[ "$ARCH" =~ ^[a-z0-9][a-z0-9-]*$ ]] || fail "Invalid package architecture."
for command in apt-get dpkg-query systemctl runuser usermod; do
  command -v "$command" >/dev/null || fail "Required command '$command' is missing."
done

APT_DIR=/etc/apt
SOURCE_FILE="$APT_DIR/sources.list.d/docker.list"
DEB822_FILE="$APT_DIR/sources.list.d/docker.sources"
KEY_FILE="$APT_DIR/keyrings/docker.gpg"
REPO_URL="https://download.docker.com/linux/$DISTRO"

# Only replace dedicated Docker source files. Refuse mixed/custom files rather
# than silently deleting another repository or creating duplicate Docker entries.
for file in "$SOURCE_FILE" "$DEB822_FILE" "$KEY_FILE"; do
  [[ ! -L "$file" ]] || fail "Refusing to replace symlink '$file'."
  [[ ! -e "$file" || -f "$file" ]] || fail "Expected a regular file: $file"
done
if [[ -f "$SOURCE_FILE" ]]; then
  awk '
    /^[[:space:]]*(#|$)/ { next }
    {
      line = $0
      sub(/^[[:space:]]*/, "", line)
      if (line !~ /^deb(-src)?[[:space:]]+/) exit 1
      sub(/^deb(-src)?[[:space:]]+/, "", line)
      if (line ~ /^\[/ && !sub(/^\[[^]]*\][[:space:]]+/, "", line)) exit 1
      split(line, parts, /[[:space:]]+/)
      if (parts[1] !~ /^https?:\/\/download[.]docker[.]com\/linux\/[a-z0-9._-]+\/?$/) exit 1
    }
  ' "$SOURCE_FILE" || fail "$SOURCE_FILE contains non-Docker entries; split them out first."
fi
if [[ -f "$DEB822_FILE" ]]; then
  awk '
    function check_uris(text, count, parts, i) {
      count = split(text, parts, /[[:space:]]+/)
      for (i = 1; i <= count; i++)
        if (parts[i] != "" && parts[i] !~ /^https?:\/\/download[.]docker[.]com\/linux\/[a-z0-9._-]+\/?$/) bad = 1
    }
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*$/ { if (stanza && !uris) bad = 1; stanza = uris = in_uris = 0; next }
    /^[[:space:]]/ { if (in_uris) check_uris($0); next }
    { stanza = 1; in_uris = 0 }
    tolower($1) == "uris:" { uris = in_uris = 1; sub(/^[^:]+:[[:space:]]*/, ""); check_uris($0) }
    END { if (stanza && !uris) bad = 1; exit bad }
  ' "$DEB822_FILE" || fail "$DEB822_FILE is not a dedicated Docker source; review it first."
fi
for file in "$APT_DIR/sources.list" "$APT_DIR"/sources.list.d/*.list "$APT_DIR"/sources.list.d/*.sources; do
  [[ -f "$file" ]] || continue
  [[ "$file" != "$SOURCE_FILE" && "$file" != "$DEB822_FILE" ]] || continue
  if awk '!/^[[:space:]]*#/ && /https?:\/\/download[.]docker[.]com\// { found = 1 } END { exit !found }' "$file"; then
    fail "Another Docker source exists in $file; consolidate it before running this script."
  fi
done

# A stale Ubuntu/trixie source breaks even the FIRST apt-get update. Save and
# temporarily disable existing Docker entries before bootstrapping dependencies.
# Backups live outside sources.list.d so APT cannot accidentally load them.
BACKUP_DIR="$(mktemp -d "$APT_DIR/docker-setup-backup.XXXXXXXX")"
OLD_SOURCES=()
KEY_SAVED=0
KEY_WRITTEN=0
SOURCE_WRITTEN=0
REPO_READY=0
cleanup() {
  local status=$? file
  if (( status != 0 && REPO_READY == 0 )); then
    printf 'Restoring previous Docker repository configuration from %s\n' "$BACKUP_DIR" >&2
    if (( SOURCE_WRITTEN )); then
      rm -f -- "$SOURCE_FILE" || printf 'Could not remove incomplete source: %s\n' "$SOURCE_FILE" >&2
    fi
    if (( ${#OLD_SOURCES[@]} )); then
      for file in "${OLD_SOURCES[@]}"; do
        cp -a -- "$BACKUP_DIR/${file##*/}" "$file" || printf 'Could not restore %s\n' "$file" >&2
      done
    fi
    if (( KEY_WRITTEN )); then
      if (( KEY_SAVED )); then
        cp -a -- "$BACKUP_DIR/docker.gpg" "$KEY_FILE" || printf 'Could not restore %s\n' "$KEY_FILE" >&2
      else
        rm -f -- "$KEY_FILE" || printf 'Could not remove incomplete key: %s\n' "$KEY_FILE" >&2
      fi
    fi
  fi
  exit "$status"
}
trap cleanup EXIT
printf 'Installing Docker for %s %s (%s), user %s.\n' "$DISTRO" "$CODENAME" "$ARCH" "$DOCKER_USER"
printf 'Docker repository backups: %s\n' "$BACKUP_DIR"
for file in "$SOURCE_FILE" "$DEB822_FILE"; do
  if [[ -f "$file" ]]; then
    mv -- "$file" "$BACKUP_DIR/${file##*/}"
    OLD_SOURCES+=("$file")
  fi
done
if [[ -f "$KEY_FILE" ]]; then
  cp -a -- "$KEY_FILE" "$BACKUP_DIR/docker.gpg"
  KEY_SAVED=1
fi

apt-get update -o APT::Update::Error-Mode=any
apt-get install --yes ca-certificates curl gnupg
install -d -m 0755 "$APT_DIR/keyrings" "$APT_DIR/sources.list.d"
curl -fsSL "$REPO_URL/gpg" -o "$BACKUP_DIR/docker.asc"
gpg --batch --yes --dearmor --output "$BACKUP_DIR/docker.gpg.new" "$BACKUP_DIR/docker.asc"
KEY_WRITTEN=1
install -m 0644 "$BACKUP_DIR/docker.gpg.new" "$KEY_FILE"
printf 'deb [arch=%s signed-by=%s] %s %s stable\n' \
  "$ARCH" "$KEY_FILE" "$REPO_URL" "$CODENAME" > "$BACKUP_DIR/docker.list.new"
SOURCE_WRITTEN=1
install -m 0644 "$BACKUP_DIR/docker.list.new" "$SOURCE_FILE"
apt-get update -o APT::Update::Error-Mode=any
REPO_READY=1

# Remove only installed conflicting packages; never uninstall docker-ce on reruns.
CONFLICTS=()
for package in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc; do
  if [[ "$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)" == 'install ok installed' ]]; then
    CONFLICTS+=("$package")
  fi
done
if (( ${#CONFLICTS[@]} )); then
  printf 'Review APT\047s removal prompt for conflicting packages: %s\n' "${CONFLICTS[*]}"
  apt-get remove "${CONFLICTS[@]}"
fi
apt-get install --yes docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker
systemctl is-active --quiet docker
printf 'Adding %s to docker (root-equivalent access).\n' "$DOCKER_USER"
usermod -aG docker -- "$DOCKER_USER"

# runuser starts a fresh process with the updated supplementary groups. Do not
# exec a login shell: that would replace this script and skip all verification.
runuser -u "$DOCKER_USER" -- docker run --rm hello-world
runuser -u "$DOCKER_USER" -- docker compose version
printf 'Docker setup complete. Log out and back in as %s before using Docker without sudo in existing sessions.\n' "$DOCKER_USER"
