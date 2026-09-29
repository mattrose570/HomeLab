#!/usr/bin/env python3
"""Privacy-conscious, dependency-free Markdown static-site generator."""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterable
from urllib.parse import urlsplit
import unicodedata

VERSION = "1.0.0"
SENTINEL = ".openclaw-md-site"
DEFAULT_EXCLUDED_PARTS = {
    ".git",
    ".github",
    ".openclaw",
    "__pycache__",
    "memory",
    "memories",
    "node_modules",
    "records",
    "record",
    "source-pdfs",
    "sources",
    "private",
    "secrets",
}
DEFAULT_EXCLUDED_FILES = {"memory.md", "user.md", ".env", "credentials.json"}
ALLOWED_LINK_SCHEMES = {"http", "https", "mailto"}


class SiteError(Exception):
    """A user-facing configuration or build error."""


def slugify(value: str, fallback: str = "item") -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or fallback


def safe_resolve(root: Path, relative: str | Path) -> Path:
    """Resolve a relative path beneath root, rejecting traversal and absolute paths."""
    root = root.resolve()
    rel = Path(relative)
    if rel.is_absolute():
        raise SiteError(f"Absolute child path is not allowed: {relative}")
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise SiteError(f"Path escapes configured root: {relative}") from exc
    return target


def sanitize_link(raw_url: str) -> tuple[str, bool]:
    """Return (safe URL, was_rejected)."""
    url = html.unescape(raw_url).strip()
    if not url or any(ord(ch) < 32 for ch in url) or "\\" in url:
        return "#unsafe-link", True
    if url.startswith("//"):
        return "#unsafe-link", True
    parsed = urlsplit(url)
    if parsed.scheme:
        if parsed.scheme.lower() not in ALLOWED_LINK_SCHEMES:
            return "#unsafe-link", True
        return url, False
    # Safe local links/fragments are allowed, but not filesystem traversal.
    path_part = parsed.path
    if path_part.startswith("/") or ".." in PurePosixPath(path_part).parts:
        return "#unsafe-link", True
    return url, False


def _pattern_matches(relative: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(relative, pattern) or (
        pattern.startswith("**/") and fnmatch.fnmatchcase(relative, pattern[3:])
    )


def _validate_glob(pattern: str) -> None:
    pure = PurePosixPath(pattern)
    if pattern.startswith("/") or ".." in pure.parts or "\\" in pattern:
        raise SiteError(f"Unsafe include/exclude pattern: {pattern!r}")


def _is_default_excluded(relative: PurePosixPath) -> bool:
    parts = relative.parts
    if any(part.startswith(".") for part in parts):
        return True
    if any(part.casefold() in DEFAULT_EXCLUDED_PARTS for part in parts[:-1]):
        return True
    if relative.name.casefold() in DEFAULT_EXCLUDED_FILES:
        return True
    return False


def _inline_basic(text: str) -> str:
    escaped = html.escape(text, quote=False)
    # Strong must run before emphasis.
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"<em>\1</em>", escaped)
    return escaped


def render_inline(text: str) -> str:
    """Render safe inline Markdown; raw HTML is always escaped."""
    tokens: list[str] = []

    def token(value: str) -> str:
        marker = f"\x00MDTOKEN{len(tokens)}\x00"
        tokens.append(value)
        return marker

    # Code spans are literal and protected from all other transforms.
    text = re.sub(
        r"`([^`\n]+)`",
        lambda m: token(f"<code>{html.escape(m.group(1), quote=False)}</code>"),
        text,
    )

    # Markdown links. This intentionally supports one non-nested label level.
    def markdown_link(match: re.Match[str]) -> str:
        label, raw_url = match.group(1), match.group(2)
        safe_url, rejected = sanitize_link(raw_url)
        attrs = ' class="unsafe-link" aria-label="Unsafe link removed"' if rejected else ""
        if not rejected and urlsplit(safe_url).scheme in {"http", "https"}:
            attrs += ' rel="noopener noreferrer"'
        return token(
            f'<a href="{html.escape(safe_url, quote=True)}"{attrs}>{_inline_basic(label)}</a>'
        )

    text = re.sub(r"\[([^\]\n]+)\]\(([^\s)]+)(?:\s+[\"'][^\"']*[\"'])?\)", markdown_link, text)

    # Plain web URLs become links. Trailing sentence punctuation stays outside.
    def bare_link(match: re.Match[str]) -> str:
        raw = match.group(0)
        trailing = ""
        while raw and raw[-1] in ".,;:!?":
            trailing = raw[-1] + trailing
            raw = raw[:-1]
        safe_url, rejected = sanitize_link(raw)
        if rejected:
            return raw + trailing
        anchor = (
            f'<a href="{html.escape(safe_url, quote=True)}" '
            f'rel="noopener noreferrer">{html.escape(raw, quote=False)}</a>'
        )
        return token(anchor) + trailing

    text = re.sub(r"https?://[^\s<>\x00]+", bare_link, text)
    rendered = _inline_basic(text)
    rendered = re.sub(r" {2,}\n", "<br>\n", rendered)
    rendered = rendered.replace("\n", " ")
    for index, value in enumerate(tokens):
        rendered = rendered.replace(f"\x00MDTOKEN{index}\x00", value)
    return rendered


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", stripped)]


def _is_table_separator(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _is_block_start(lines: list[str], index: int) -> bool:
    line = lines[index]
    if not line.strip():
        return True
    if re.match(r"^ {0,3}#{1,6}\s+", line):
        return True
    if re.match(r"^ {0,3}(```|~~~)", line):
        return True
    if re.match(r"^ {0,3}>\s?", line):
        return True
    if re.match(r"^\s*(?:[-+*]|\d+[.)])\s+", line):
        return True
    if re.match(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", line):
        return True
    if index + 1 < len(lines) and "|" in line and _is_table_separator(lines[index + 1]):
        return True
    return False


class MarkdownRenderer:
    def __init__(self) -> None:
        self._heading_counts: dict[str, int] = {}
        self.headings: list[dict[str, Any]] = []
        self.title = "Untitled document"

    def _heading_id(self, heading: str) -> str:
        base = slugify(re.sub(r"[`*_]", "", heading), "section")
        count = self._heading_counts.get(base, 0) + 1
        self._heading_counts[base] = count
        return base if count == 1 else f"{base}-{count}"

    def render(self, markdown_text: str, *, drop_first_h1: bool = False) -> str:
        text = markdown_text.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")
        output: list[str] = []
        index = 0
        saw_heading = False
        dropped_title = False

        while index < len(lines):
            line = lines[index]
            if not line.strip():
                index += 1
                continue

            # Convert one exact, common print-break directive into generator-owned safe HTML.
            # All other raw HTML remains text and is escaped by render_inline().
            if re.fullmatch(
                r'\s*<div\s+style=["\']page-break-after:\s*always;?["\']\s*>\s*</div>\s*',
                line,
                flags=re.IGNORECASE,
            ):
                output.append('<div class="page-break" aria-hidden="true"></div>')
                index += 1
                continue

            fence = re.match(r"^ {0,3}(```|~~~)\s*([A-Za-z0-9_+-]*)\s*$", line)
            if fence:
                marker, language = fence.group(1), fence.group(2)
                code_lines: list[str] = []
                index += 1
                while index < len(lines) and not re.match(
                    rf"^ {{0,3}}{re.escape(marker)}\s*$", lines[index]
                ):
                    code_lines.append(lines[index])
                    index += 1
                if index < len(lines):
                    index += 1
                lang_attr = f' class="language-{html.escape(language, quote=True)}"' if language else ""
                output.append(
                    f'<pre><code{lang_attr}>{html.escape(chr(10).join(code_lines), quote=False)}</code></pre>'
                )
                continue

            heading = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
            if heading:
                level = len(heading.group(1))
                raw_text = heading.group(2).strip()
                heading_id = self._heading_id(raw_text)
                plain_heading = re.sub(r"[`*_]", "", raw_text).strip()
                if not saw_heading:
                    self.title = plain_heading
                    saw_heading = True
                if drop_first_h1 and level == 1 and not dropped_title and len(self.headings) == 0:
                    dropped_title = True
                    index += 1
                    continue
                self.headings.append({"level": level, "text": plain_heading, "id": heading_id})
                output.append(
                    f'<h{level} id="{heading_id}">{render_inline(raw_text)}'
                    f'<a class="heading-anchor" href="#{heading_id}" aria-label="Link to this section">#</a>'
                    f"</h{level}>"
                )
                index += 1
                continue

            if re.match(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", line):
                output.append("<hr>")
                index += 1
                continue

            if index + 1 < len(lines) and "|" in line and _is_table_separator(lines[index + 1]):
                headers = _split_table_row(line)
                aligns: list[str] = []
                for cell in _split_table_row(lines[index + 1]):
                    if cell.startswith(":") and cell.endswith(":"):
                        aligns.append("center")
                    elif cell.endswith(":"):
                        aligns.append("right")
                    else:
                        aligns.append("left")
                index += 2
                rows: list[list[str]] = []
                while index < len(lines) and lines[index].strip() and "|" in lines[index]:
                    rows.append(_split_table_row(lines[index]))
                    index += 1
                parts = ['<div class="table-wrap" tabindex="0" role="region" aria-label="Scrollable table"><table><thead><tr>']
                for col, cell in enumerate(headers):
                    align = aligns[col] if col < len(aligns) else "left"
                    parts.append(f'<th class="align-{align}" scope="col">{render_inline(cell)}</th>')
                parts.append("</tr></thead><tbody>")
                for row in rows:
                    parts.append("<tr>")
                    for col in range(len(headers)):
                        cell = row[col] if col < len(row) else ""
                        align = aligns[col] if col < len(aligns) else "left"
                        parts.append(f'<td class="align-{align}">{render_inline(cell)}</td>')
                    parts.append("</tr>")
                parts.append("</tbody></table></div>")
                output.append("".join(parts))
                continue

            if re.match(r"^ {0,3}>\s?", line):
                quoted: list[str] = []
                while index < len(lines):
                    match = re.match(r"^ {0,3}>\s?(.*)$", lines[index])
                    if not match:
                        break
                    quoted.append(match.group(1))
                    index += 1
                inner = MarkdownRenderer().render("\n".join(quoted))
                output.append(f"<blockquote>{inner}</blockquote>")
                continue

            list_match = re.match(r"^\s*((?:[-+*])|(?:\d+[.)]))\s+(.+)$", line)
            if list_match:
                ordered = bool(re.match(r"\d", list_match.group(1)))
                start = re.match(r"(\d+)", list_match.group(1))
                list_tag = "ol" if ordered else "ul"
                start_attr = f' start="{int(start.group(1))}"' if ordered and start and int(start.group(1)) != 1 else ""
                items: list[str] = []
                while index < len(lines):
                    item = re.match(r"^\s*((?:[-+*])|(?:\d+[.)]))\s+(.+)$", lines[index])
                    if not item or bool(re.match(r"\d", item.group(1))) != ordered:
                        break
                    content = item.group(2).strip()
                    task = re.match(r"^\[([ xX])\]\s*(.*)$", content)
                    if task:
                        checked = bool(task.group(1).strip())
                        checked_attr = " checked" if checked else ""
                        content_html = (
                            f'<input class="task-checkbox" type="checkbox" disabled{checked_attr} '
                            f'aria-label="{("Completed" if checked else "Not completed")}"> '
                            f"{render_inline(task.group(2))}"
                        )
                    else:
                        content_html = render_inline(content)
                    items.append(f"<li>{content_html}</li>")
                    index += 1
                output.append(f"<{list_tag}{start_attr}>" + "".join(items) + f"</{list_tag}>")
                continue

            def paragraph_line(value: str) -> str:
                # Preserve Markdown's two-trailing-space hard break while trimming
                # incidental indentation around ordinary prose.
                hard_break = value.endswith("  ")
                cleaned = value.strip()
                return cleaned + ("  " if hard_break else "")

            paragraph_lines = [paragraph_line(line)]
            index += 1
            while index < len(lines) and not _is_block_start(lines, index):
                paragraph_lines.append(paragraph_line(lines[index]))
                index += 1
            output.append(f"<p>{render_inline(chr(10).join(paragraph_lines))}</p>")

        return "\n".join(output)


def extract_prepared_date(markdown_text: str) -> str:
    match = re.search(r"^\*\*Prepared:\*\*\s*(.+?)\s*$", markdown_text, re.MULTILINE)
    if match:
        return re.sub(r"[*_`]", "", match.group(1)).strip()
    return "Date not stated"


def _plain_search_text(markdown_text: str) -> str:
    value = re.sub(r"```.*?```", " ", markdown_text, flags=re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[#>*_`|~-]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def load_config(config_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SiteError(f"Config not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise SiteError(f"Invalid JSON in {config_path.name}: line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise SiteError("Config root must be a JSON object")
    if not isinstance(data.get("sources"), list) or not data["sources"]:
        raise SiteError("Config must define a non-empty 'sources' list")
    if not isinstance(data.get("output_dir"), str) or not data["output_dir"].strip():
        raise SiteError("Config must define 'output_dir'")
    return data


def _config_path(base: Path, value: str, name: str) -> Path:
    path = Path(value).expanduser()
    resolved = path.resolve() if path.is_absolute() else (base / path).resolve()
    if resolved == Path(resolved.anchor):
        raise SiteError(f"Refusing to use filesystem root as {name}")
    return resolved


def discover_sources(config: dict[str, Any], config_path: Path) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[Path] = set()
    global_excludes = config.get("exclude", [])
    if not isinstance(global_excludes, list) or not all(isinstance(x, str) for x in global_excludes):
        raise SiteError("'exclude' must be a list of glob strings")
    for pattern in global_excludes:
        _validate_glob(pattern)

    for source_index, source in enumerate(config["sources"]):
        if not isinstance(source, dict):
            raise SiteError(f"sources[{source_index}] must be an object")
        if not isinstance(source.get("root"), str):
            raise SiteError(f"sources[{source_index}] must define a root")
        includes = source.get("include")
        if not isinstance(includes, list) or not includes or not all(isinstance(x, str) for x in includes):
            raise SiteError(
                f"sources[{source_index}] must define a non-empty include list; implicit publication is disabled"
            )
        excludes = source.get("exclude", [])
        if not isinstance(excludes, list) or not all(isinstance(x, str) for x in excludes):
            raise SiteError(f"sources[{source_index}].exclude must be a list of glob strings")
        for pattern in [*includes, *excludes]:
            _validate_glob(pattern)

        root = _config_path(config_path.parent, source["root"], f"sources[{source_index}].root")
        if not root.is_dir():
            raise SiteError(f"Source root is not a directory: {source['root']}")

        for candidate in root.rglob("*.md"):
            resolved = candidate.resolve()
            try:
                rel = resolved.relative_to(root)
            except ValueError:
                # Symlink escaped the source root.
                continue
            rel_posix = rel.as_posix()
            if _is_default_excluded(PurePosixPath(rel_posix)):
                continue
            ancestry = [candidate]
            cursor = candidate.parent
            while cursor != root and root in cursor.parents:
                ancestry.append(cursor)
                cursor = cursor.parent
            if any(part.is_symlink() for part in ancestry):
                continue
            if not any(_pattern_matches(rel_posix, pattern) for pattern in includes):
                continue
            if any(_pattern_matches(rel_posix, pattern) for pattern in [*global_excludes, *excludes]):
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(
                {
                    "path": resolved,
                    "relative": rel_posix,
                    "source_id": f"{source_index}:{rel_posix}",
                    "source_name": resolved.name,
                }
            )
    found.sort(key=lambda item: item["source_id"])
    if not found:
        raise SiteError("No Markdown files matched the configured include globs")
    return found


def assign_doc_slugs(sources: list[dict[str, Any]]) -> None:
    used: set[str] = set()
    for source in sorted(sources, key=lambda item: item["source_id"]):
        stem_path = str(PurePosixPath(source["relative"]).with_suffix(""))
        base = slugify(stem_path.replace("/", "-"), "document")
        candidate = base
        if candidate in used:
            digest = hashlib.sha256(source["source_id"].encode("utf-8")).hexdigest()[:8]
            candidate = f"{base}-{digest}"
            suffix = 2
            while candidate in used:
                candidate = f"{base}-{digest}-{suffix}"
                suffix += 1
        source["slug"] = candidate
        used.add(candidate)


STYLE = r"""
:root {
  color-scheme: light;
  --ink: #172033; --muted: #536076; --paper: #ffffff; --canvas: #eef2f7;
  --navy: #14345f; --blue: #1769aa; --blue-soft: #e7f2fb; --line: #c9d3df;
  --warning-bg: #fff4d6; --warning-line: #9a6700; --focus: #d63f00;
  --sidebar: 19rem; --content: 72rem;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 1.25rem; }
body { margin: 0; overflow-x: hidden; background: var(--canvas); color: var(--ink); font: 17px/1.62 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
a { color: #075a9c; text-decoration-thickness: .09em; text-underline-offset: .14em; }
a:hover { color: #003d70; }
a:focus-visible, button:focus-visible, input:focus-visible, [tabindex="0"]:focus-visible { outline: 3px solid var(--focus); outline-offset: 3px; }
.skip-link { position: fixed; z-index: 100; left: .75rem; top: -5rem; padding: .65rem 1rem; background: #fff; color: #000; border: 2px solid #000; }
.skip-link:focus { top: .75rem; }
.privacy-banner { margin: 0; padding: .72rem 1.1rem; background: var(--warning-bg); border-bottom: 3px solid var(--warning-line); color: #3f3100; font-size: .94rem; text-align: center; }
.privacy-banner strong { color: #291f00; }
.mobile-bar { display: none; align-items: center; justify-content: space-between; gap: 1rem; padding: .75rem 1rem; background: var(--navy); color: #fff; }
.mobile-bar a { color: #fff; font-weight: 750; text-decoration: none; }
.menu-button, .action-button { border: 1px solid #8ba0ba; border-radius: .42rem; background: #fff; color: #163458; font: inherit; font-weight: 700; padding: .48rem .72rem; cursor: pointer; }
.menu-button { background: transparent; border-color: #fff; color: #fff; }
.site-shell { min-height: 100vh; }
.sidebar { position: fixed; inset: 0 auto 0 0; width: var(--sidebar); overflow-y: auto; background: var(--navy); color: #fff; padding: 1.35rem 1.1rem 2rem; }
.sidebar a { color: #fff; }
.site-title { display: block; font-size: 1.17rem; font-weight: 800; line-height: 1.25; text-decoration: none; margin-bottom: 1.25rem; }
.sidebar label, .sidebar h2 { display: block; margin: 1.05rem 0 .38rem; font-size: .78rem; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; color: #d8e7f8; }
.search-input { width: 100%; border: 2px solid #9fb3ca; border-radius: .4rem; padding: .55rem .62rem; font: inherit; color: #111; background: #fff; }
.nav-list, .toc-list { list-style: none; margin: .35rem 0; padding: 0; }
.nav-list li, .toc-list li { margin: .14rem 0; }
.nav-list a, .toc-list a { display: block; padding: .34rem .42rem; border-radius: .3rem; line-height: 1.3; text-decoration: none; }
.nav-list a:hover, .toc-list a:hover, .nav-list a[aria-current="page"] { background: #27517e; }
.toc-list .toc-level-2 { padding-left: .75rem; }
.toc-list .toc-level-3, .toc-list .toc-level-4, .toc-list .toc-level-5, .toc-list .toc-level-6 { padding-left: 1.35rem; font-size: .92rem; }
.search-status { min-height: 1.5em; margin: .35rem 0; color: #d8e7f8; font-size: .85rem; }
.main { min-width: 0; margin-left: var(--sidebar); padding: 2rem clamp(1rem, 4vw, 4rem) 4rem; }
.document, .index-panel { min-width: 0; max-width: var(--content); margin: 0 auto; background: var(--paper); border: 1px solid var(--line); border-radius: .7rem; box-shadow: 0 5px 24px rgba(28, 45, 72, .09); padding: clamp(1.2rem, 4vw, 3.3rem); }
.document-header { min-width: 0; padding-bottom: 1.35rem; border-bottom: 2px solid var(--line); margin-bottom: 2rem; }
h1 { color: #102d51; font-size: clamp(2rem, 5vw, 3rem); line-height: 1.13; margin: 0 0 .75rem; letter-spacing: -.025em; overflow-wrap: anywhere; }
h2 { color: #143f6d; font-size: 1.68rem; line-height: 1.25; margin: 2.4rem 0 .8rem; border-bottom: 1px solid var(--line); padding-bottom: .32rem; }
h3 { color: #1c4b77; font-size: 1.3rem; line-height: 1.3; margin: 1.8rem 0 .55rem; }
h4, h5, h6 { color: #243f5d; line-height: 1.3; margin: 1.5rem 0 .45rem; }
.heading-anchor { opacity: 0; margin-left: .45rem; font-size: .7em; text-decoration: none; }
h1:hover .heading-anchor, h2:hover .heading-anchor, h3:hover .heading-anchor, h4:hover .heading-anchor, h5:hover .heading-anchor, h6:hover .heading-anchor, .heading-anchor:focus { opacity: 1; }
p { margin: .7rem 0 1rem; }
li { margin: .35rem 0; }
hr { border: 0; border-top: 2px solid var(--line); margin: 2rem 0; }
blockquote { margin: 1.1rem 0; padding: .65rem 1rem; border-left: 5px solid var(--blue); background: var(--blue-soft); }
blockquote > :first-child { margin-top: 0; } blockquote > :last-child { margin-bottom: 0; }
code { font: .92em ui-monospace, SFMono-Regular, Consolas, monospace; background: #edf1f5; border-radius: .24rem; padding: .08rem .28rem; }
pre { overflow-x: auto; padding: 1rem; border-radius: .42rem; background: #172033; color: #f5f7fa; }
pre code { background: transparent; padding: 0; }
.table-wrap { max-width: 100%; overflow-x: auto; margin: 1.2rem 0 1.6rem; border: 1px solid #abb9c8; border-radius: .4rem; }
table { width: 100%; border-collapse: collapse; min-width: 42rem; font-size: .94rem; line-height: 1.45; }
th { background: #e5edf6; color: #122f50; text-align: left; }
th, td { border: 1px solid #bec9d5; padding: .62rem .68rem; vertical-align: top; }
tbody tr:nth-child(even) { background: #f7f9fb; }
.align-center { text-align: center; } .align-right { text-align: right; }
.task-checkbox { width: 1.05rem; height: 1.05rem; vertical-align: -.14rem; accent-color: var(--blue); }
.doc-meta { display: flex; flex-wrap: wrap; gap: .45rem 1.25rem; min-width: 0; color: var(--muted); font-size: .93rem; }
.doc-meta span, .doc-meta cite { min-width: 0; overflow-wrap: anywhere; word-break: break-word; }
.doc-actions { display: flex; flex-wrap: wrap; gap: .65rem; margin-top: 1rem; }
.source-citation { margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--line); color: var(--muted); font-size: .9rem; overflow-wrap: anywhere; }
.page-break { height: 0; margin: 2rem 0; border-top: 2px dashed var(--line); break-after: page; }
.card-grid { display: grid; gap: 1rem; margin-top: 1.5rem; }
.doc-card { border: 1px solid var(--line); border-radius: .55rem; padding: 1rem 1.15rem; background: #fbfcfe; }
.doc-card h2 { margin: 0 0 .4rem; border: 0; padding: 0; font-size: 1.25rem; }
.doc-card p { margin: .3rem 0; }
.back-to-top { position: fixed; right: 1rem; bottom: 1rem; z-index: 30; box-shadow: 0 2px 10px rgba(0,0,0,.2); }
.unsafe-link { text-decoration: line-through; cursor: not-allowed; }
.visually-hidden { position: absolute !important; width: 1px; height: 1px; overflow: hidden; clip: rect(1px, 1px, 1px, 1px); white-space: nowrap; }
.no-results { padding: .8rem; color: var(--muted); }
@media (max-width: 850px) {
  .mobile-bar { display: flex; position: sticky; top: 0; z-index: 50; min-width: 0; }
  .mobile-bar a { min-width: 0; overflow-wrap: anywhere; }
  .mobile-bar .menu-button { flex: none; }
  .sidebar { z-index: 60; transform: translateX(-105%); transition: transform .2s ease; box-shadow: 6px 0 24px rgba(0,0,0,.28); }
  .sidebar.open { transform: translateX(0); }
  .main { margin-left: 0; padding: 1rem .65rem 3.5rem; }
  .document, .index-panel { border-radius: .4rem; padding: 1.1rem; }
  body.nav-open::after { content: ""; position: fixed; z-index: 55; inset: 0; background: rgba(0,0,0,.44); }
}
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } .sidebar { transition: none; } }
@media print {
  @page { margin: .55in; }
  body { background: #fff; color: #000; font-size: 10.5pt; line-height: 1.38; }
  .sidebar, .mobile-bar, .doc-actions, .back-to-top, .skip-link { display: none !important; }
  .main { margin: 0; padding: 0; }
  .document, .index-panel { max-width: none; border: 0; box-shadow: none; padding: 0; }
  .privacy-banner { border: 1px solid #7a6500; padding: .25rem; font-size: 8.5pt; }
  a { color: #000; text-decoration: none; } a[href^="http"]::after { content: " (" attr(href) ")"; font-size: 8pt; overflow-wrap: anywhere; }
  h1, h2, h3 { break-after: avoid; } table, blockquote, pre { break-inside: avoid; }
  .page-break { height: 0; margin: 0; border: 0; break-after: page; }
  .table-wrap { overflow: visible; border: 0; } table { min-width: 0; font-size: 8pt; }
  .heading-anchor { display: none; }
}
"""

SCRIPT = r"""
(() => {
  'use strict';
  const sidebar = document.querySelector('.sidebar');
  const menu = document.querySelector('[data-menu-button]');
  const closeNav = () => {
    if (!sidebar || !menu) return;
    sidebar.classList.remove('open');
    document.body.classList.remove('nav-open');
    menu.setAttribute('aria-expanded', 'false');
  };
  if (menu && sidebar) {
    menu.addEventListener('click', () => {
      const open = !sidebar.classList.contains('open');
      sidebar.classList.toggle('open', open);
      document.body.classList.toggle('nav-open', open);
      menu.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeNav(); });
    sidebar.addEventListener('click', (event) => { if (event.target.closest('a') && innerWidth <= 850) closeNav(); });
    document.body.addEventListener('click', (event) => {
      if (document.body.classList.contains('nav-open') && !sidebar.contains(event.target) && !menu.contains(event.target)) closeNav();
    });
  }
  document.querySelectorAll('[data-print]').forEach(button => button.addEventListener('click', () => window.print()));
  document.querySelectorAll('[data-top]').forEach(button => button.addEventListener('click', () => window.scrollTo({top: 0, behavior: 'smooth'})));

  const input = document.querySelector('[data-search]');
  const status = document.querySelector('[data-search-status]');
  const navItems = [...document.querySelectorAll('[data-doc-nav-item]')];
  const cards = [...document.querySelectorAll('[data-doc-card]')];
  if (input) {
    const runSearch = () => {
      const query = input.value.trim().toLocaleLowerCase();
      let visible = 0;
      navItems.forEach(item => {
        const matches = !query || (item.dataset.search || '').includes(query);
        item.hidden = !matches;
        if (matches) visible += 1;
      });
      cards.forEach(card => {
        const matches = !query || (card.dataset.search || '').includes(query);
        card.hidden = !matches;
      });
      if (status) status.textContent = query ? `${visible} document${visible === 1 ? '' : 's'} found` : `${navItems.length} document${navItems.length === 1 ? '' : 's'}`;
    };
    input.addEventListener('input', runSearch);
    runSearch();
  }
})();
"""

CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src 'none'; connect-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"


def _privacy_text(config: dict[str, Any]) -> str:
    site = config.get("site", {})
    if isinstance(site, dict) and isinstance(site.get("privacy_notice"), str):
        return site["privacy_notice"]
    return "Private health document: this site may contain PII/PHI. Keep it private and use access controls when hosting."


def _doc_nav(docs: list[dict[str, Any]], current_slug: str | None) -> str:
    items: list[str] = []
    for doc in docs:
        current = ' aria-current="page"' if doc["slug"] == current_slug else ""
        search = html.escape((doc["title"] + " " + doc["search_text"]).lower(), quote=True)
        items.append(
            f'<li data-doc-nav-item data-search="{search}"><a href="{("" if current_slug is None else "../")}docs/{doc["slug"]}.html"{current}>'
            f'{html.escape(doc["title"])}</a></li>'
        )
    return "".join(items)


def _toc(headings: list[dict[str, Any]]) -> str:
    if not headings:
        return '<p class="search-status">No section headings.</p>'
    return "".join(
        f'<li class="toc-level-{heading["level"]}"><a href="#{heading["id"]}">{html.escape(heading["text"])}</a></li>'
        for heading in headings
    )


def _page_template(
    *,
    config: dict[str, Any],
    page_title: str,
    sidebar_html: str,
    main_html: str,
    relative_home: str,
) -> str:
    site = config.get("site", {}) if isinstance(config.get("site"), dict) else {}
    site_title = str(site.get("title", "Private document library"))
    privacy = _privacy_text(config)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive, nosnippet">
<meta http-equiv="Content-Security-Policy" content="{html.escape(CSP, quote=True)}">
<title>{html.escape(page_title)} · {html.escape(site_title)}</title>
<style>{STYLE}</style>
</head>
<body id="top">
<a class="skip-link" href="#main-content">Skip to content</a>
<p class="privacy-banner"><strong>Privacy notice:</strong> {html.escape(privacy)} Robots directives reduce indexing requests but are <strong>not access control</strong>.</p>
<header class="mobile-bar"><a href="{relative_home}index.html">{html.escape(site_title)}</a><button class="menu-button" type="button" data-menu-button aria-controls="site-sidebar" aria-expanded="false">Menu</button></header>
<div class="site-shell">
<aside class="sidebar" id="site-sidebar" aria-label="Site navigation">
<a class="site-title" href="{relative_home}index.html">{html.escape(site_title)}</a>
<label for="site-search">Search documents</label>
<input class="search-input" id="site-search" data-search type="search" autocomplete="off" placeholder="Search this library">
<p class="search-status" data-search-status aria-live="polite"></p>
{sidebar_html}
</aside>
<main class="main" id="main-content" tabindex="-1">{main_html}</main>
</div>
<button class="action-button back-to-top" type="button" data-top aria-label="Back to top">↑ Top</button>
<script>{SCRIPT}</script>
</body>
</html>
"""


def _build_docs(source_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assign_doc_slugs(source_items)
    docs: list[dict[str, Any]] = []
    for source in source_items:
        markdown_text = source["path"].read_text(encoding="utf-8")
        renderer = MarkdownRenderer()
        body_html = renderer.render(markdown_text, drop_first_h1=True)
        docs.append(
            {
                **source,
                "title": renderer.title,
                "date": extract_prepared_date(markdown_text),
                "body_html": body_html,
                "headings": renderer.headings,
                "search_text": _plain_search_text(markdown_text),
            }
        )
    docs.sort(key=lambda item: (item["title"].casefold(), item["slug"]))
    return docs


def _safe_clean_output(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    sentinel = output_dir / SENTINEL
    if not sentinel.is_file() or not sentinel.read_text(encoding="utf-8").startswith("openclaw-md-site"):
        raise SiteError(
            f"Refusing --clean because output directory lacks the {SENTINEL} safety marker: {output_dir}"
        )
    shutil.rmtree(output_dir)


def build_site(config_path: Path, *, clean: bool = False) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_config(config_path)
    output_dir = _config_path(config_path.parent, config["output_dir"], "output_dir")
    if output_dir == config_path.parent or config_path.parent in output_dir.parents and output_dir.name == "":
        raise SiteError("Unsafe output directory")
    if clean:
        _safe_clean_output(output_dir)
    elif output_dir.exists() and any(output_dir.iterdir()):
        raise SiteError(
            "Output directory is not empty. Re-run with --clean so removed documents cannot remain as stale files: "
            f"{output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_dir = safe_resolve(output_dir, "docs")
    docs_dir.mkdir(parents=True, exist_ok=True)

    sources = discover_sources(config, config_path)
    docs = _build_docs(sources)
    site = config.get("site", {}) if isinstance(config.get("site"), dict) else {}
    site_title = str(site.get("title", "Private document library"))

    nav_for_index = _doc_nav(docs, None)
    cards: list[str] = []
    for doc in docs:
        searchable = html.escape((doc["title"] + " " + doc["search_text"]).lower(), quote=True)
        cards.append(
            f'<article class="doc-card" data-doc-card data-search="{searchable}">'
            f'<h2><a href="docs/{doc["slug"]}.html">{html.escape(doc["title"])}</a></h2>'
            f'<p><strong>Prepared:</strong> {html.escape(doc["date"])}</p>'
            f'<p><strong>Source:</strong> <cite>{html.escape(doc["source_name"])}</cite></p>'
            f"</article>"
        )
    index_main = (
        '<section class="index-panel">'
        f'<h1>{html.escape(site_title)}</h1>'
        '<p>This static library contains only Markdown files explicitly selected in its build configuration. '
        'It uses no analytics, external fonts, CDN assets, cookies, or automatic network requests.</p>'
        '<p><strong>Keep medical and VA documents private.</strong> If deployment is necessary, use real authentication and authorization. '
        '<code>robots.txt</code> and no-index metadata are courtesy signals—not security controls.</p>'
        '<div class="doc-actions"><button class="action-button" type="button" data-print>Print / Save PDF</button></div>'
        '<div class="card-grid">' + "".join(cards) + "</div></section>"
    )
    index_sidebar = '<h2>Documents</h2><ul class="nav-list">' + nav_for_index + "</ul>"
    index_html = _page_template(
        config=config,
        page_title="Documents",
        sidebar_html=index_sidebar,
        main_html=index_main,
        relative_home="",
    )
    safe_resolve(output_dir, "index.html").write_text(index_html, encoding="utf-8")

    for doc in docs:
        sidebar = (
            '<h2>Documents</h2><ul class="nav-list">'
            + _doc_nav(docs, doc["slug"])
            + '</ul><h2>On this page</h2><ul class="toc-list">'
            + _toc(doc["headings"])
            + "</ul>"
        )
        main = (
            '<article class="document">'
            '<header class="document-header">'
            f'<h1>{html.escape(doc["title"])}</h1>'
            '<div class="doc-meta">'
            f'<span><strong>Prepared:</strong> {html.escape(doc["date"])}</span>'
            f'<span><strong>Source:</strong> <cite>{html.escape(doc["source_name"])}</cite></span>'
            '</div><div class="doc-actions">'
            '<button class="action-button" type="button" data-print>Print / Save PDF</button>'
            '<a class="action-button" href="../index.html">All documents</a>'
            '</div></header>'
            f'<div class="markdown-body">{doc["body_html"]}</div>'
            f'<footer class="source-citation">Rendered from <cite>{html.escape(doc["source_name"])}</cite>. '
            'The local filesystem path is intentionally omitted.</footer>'
            "</article>"
        )
        page = _page_template(
            config=config,
            page_title=doc["title"],
            sidebar_html=sidebar,
            main_html=main,
            relative_home="../",
        )
        safe_resolve(docs_dir, f'{doc["slug"]}.html').write_text(page, encoding="utf-8")

    search_index = [
        {
            "title": doc["title"],
            "url": f'docs/{doc["slug"]}.html',
            "date": doc["date"],
            "source": doc["source_name"],
            "headings": [heading["text"] for heading in doc["headings"]],
            "text": doc["search_text"],
        }
        for doc in docs
    ]
    safe_resolve(output_dir, "search-index.json").write_text(
        json.dumps(search_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    safe_resolve(output_dir, "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    safe_resolve(output_dir, SENTINEL).write_text(
        f"openclaw-md-site {VERSION}\nGenerated static output; safe marker for --clean.\n", encoding="utf-8"
    )
    generated = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    safe_resolve(output_dir, "build-info.json").write_text(
        json.dumps(
            {
                "generator": f"openclaw-md-site {VERSION}",
                "generated_utc": generated,
                "document_count": len(docs),
                "documents": [
                    {"title": doc["title"], "url": f'docs/{doc["slug"]}.html', "source": doc["source_name"]}
                    for doc in docs
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"output_dir": output_dir, "documents": docs}


def serve_site(config_path: Path, host: str, port: int, do_build: bool, clean: bool) -> None:
    if do_build:
        result = build_site(config_path, clean=clean)
        output_dir = result["output_dir"]
    else:
        config = load_config(config_path.resolve())
        output_dir = _config_path(config_path.resolve().parent, config["output_dir"], "output_dir")
    if not (output_dir / "index.html").is_file():
        raise SiteError("Built index.html not found; run the build command first or pass --build")

    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(*args, directory=str(output_dir), **kwargs)
    try:
        with ThreadingHTTPServer((host, port), handler) as server:
            print(f"Serving {output_dir} at http://{host}:{server.server_port}/")
            print("Press Ctrl-C to stop.")
            server.serve_forever()
    except OSError as exc:
        raise SiteError(f"Could not start server on {host}:{port}: {exc}") from exc
    except KeyboardInterrupt:
        print("\nServer stopped.")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Build the configured static site")
    build_parser.add_argument("--config", required=True, type=Path, help="Path to JSON config")
    build_parser.add_argument(
        "--clean",
        action="store_true",
        help=f"Remove a previous generated output only when its {SENTINEL} marker exists",
    )

    serve_parser = subparsers.add_parser("serve", help="Serve already-built output locally")
    serve_parser.add_argument("--config", required=True, type=Path, help="Path to JSON config")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000; use 0 for any free port)")
    serve_parser.add_argument("--build", action="store_true", help="Build before serving")
    serve_parser.add_argument("--clean", action="store_true", help="With --build, safely clean previous output")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "build":
            result = build_site(args.config, clean=args.clean)
            print(f"Built {len(result['documents'])} document(s) in {result['output_dir']}")
            for doc in result["documents"]:
                print(f"  docs/{doc['slug']}.html")
        elif args.command == "serve":
            if args.clean and not args.build:
                raise SiteError("--clean requires --build for the serve command")
            serve_site(args.config, args.host, args.port, args.build, args.clean)
        return 0
    except (SiteError, UnicodeDecodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
