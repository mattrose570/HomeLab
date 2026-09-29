import json
from pathlib import Path
import tempfile
import unittest

import mdsite


class SafetyTests(unittest.TestCase):
    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(mdsite.SiteError):
                mdsite.safe_resolve(root, "../outside.html")
            with self.assertRaises(mdsite.SiteError):
                mdsite.safe_resolve(root, "/tmp/outside.html")

    def test_unsafe_links_and_raw_html_are_never_active(self):
        rendered = mdsite.MarkdownRenderer().render(
            "[bad](javascript:alert(1))\n\n<script>alert('x')</script>\n\n"
            "<div style=\"page-break-after: always;\"></div>\n\n[ok](https://example.com)"
        )
        self.assertNotIn('href="javascript:', rendered)
        self.assertIn('href="#unsafe-link"', rendered)
        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn("<script>alert", rendered)
        self.assertIn('<div class="page-break"', rendered)
        self.assertNotIn('style="page-break-after', rendered)
        self.assertIn('href="https://example.com"', rendered)

    def test_duplicate_heading_and_document_slugs_are_deterministic(self):
        renderer = mdsite.MarkdownRenderer()
        rendered = renderer.render("# Repeat\n\n## Repeat\n\n## Repeat")
        self.assertIn('id="repeat"', rendered)
        self.assertIn('id="repeat-2"', rendered)
        self.assertIn('id="repeat-3"', rendered)

        sources = [
            {"relative": "a-b.md", "source_id": "0:a-b.md"},
            {"relative": "a/b.md", "source_id": "1:a/b.md"},
        ]
        mdsite.assign_doc_slugs(sources)
        self.assertEqual(sources[0]["slug"], "a-b")
        self.assertRegex(sources[1]["slug"], r"^a-b-[0-9a-f]{8}$")
        first = [item["slug"] for item in sources]
        mdsite.assign_doc_slugs(sources)
        self.assertEqual(first, [item["slug"] for item in sources])


class RenderingTests(unittest.TestCase):
    def test_basic_markdown_features(self):
        source = """# Heading

**bold** and *emphasis* with `code` and [link](https://example.com).

- item
- [x] checked

1. first
2. second

> quoted text

| Name | Value |
|---|---:|
| A | 1 |

```python
print("safe")
```
"""
        rendered = mdsite.MarkdownRenderer().render(source)
        for expected in (
            "<h1",
            "<strong>bold</strong>",
            "<em>emphasis</em>",
            "<code>code</code>",
            "<ul>",
            "type=\"checkbox\"",
            "<ol>",
            "<blockquote>",
            "<table>",
            "language-python",
        ):
            self.assertIn(expected, rendered)

    def test_two_space_hard_line_break_is_preserved(self):
        rendered = mdsite.MarkdownRenderer().render("First line  \nSecond line")
        self.assertIn("First line<br>", rendered)
        self.assertIn("Second line", rendered)


class BuildTests(unittest.TestCase):
    def test_build_output_is_static_private_and_path_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = root / "content"
            content.mkdir()
            source = content / "prep.md"
            source.write_text(
                "# Appointment Prep\n\n**Prepared:** September 25, 2026\n\n"
                "## Safety\n\nUse this safely.\n\n## Safety\n\nDuplicate heading.\n",
                encoding="utf-8",
            )
            output = root / "site"
            config = root / "site.json"
            config.write_text(
                json.dumps(
                    {
                        "site": {"title": "Private docs"},
                        "output_dir": "site",
                        "sources": [{"root": "content", "include": ["prep.md"]}],
                    }
                ),
                encoding="utf-8",
            )
            result = mdsite.build_site(config)
            self.assertEqual(len(result["documents"]), 1)
            page = output / "docs" / "prep.html"
            self.assertTrue(page.is_file())
            self.assertTrue((output / "index.html").is_file())
            self.assertEqual((output / "robots.txt").read_text(), "User-agent: *\nDisallow: /\n")
            generated_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in output.rglob("*")
                if path.is_file()
            )
            self.assertNotIn(str(root), generated_text)
            self.assertIn("Appointment Prep", generated_text)
            self.assertIn('id="safety-2"', generated_text)
            page_text = page.read_text(encoding="utf-8")
            self.assertIn("Content-Security-Policy", page_text)
            self.assertIn("overflow-wrap: anywhere", page_text)
            self.assertIn("overflow-x: hidden", page_text)

            # A non-clean rebuild fails rather than leaving stale, unlisted documents.
            with self.assertRaises(mdsite.SiteError):
                mdsite.build_site(config)

            # Safe cleaning works only for output created by this generator.
            second = mdsite.build_site(config, clean=True)
            self.assertEqual(len(second["documents"]), 1)

    def test_broad_glob_still_excludes_memory_records_and_hidden_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = root / "content"
            (content / "records").mkdir(parents=True)
            (content / ".hidden").mkdir()
            (content / "public").mkdir()
            (content / "public" / "ok.md").write_text("# OK", encoding="utf-8")
            (content / "records" / "medical.md").write_text("# secret", encoding="utf-8")
            (content / ".hidden" / "note.md").write_text("# hidden", encoding="utf-8")
            (content / "MEMORY.md").write_text("# memory", encoding="utf-8")
            config_path = root / "site.json"
            config = {
                "output_dir": "site",
                "sources": [{"root": "content", "include": ["**/*.md"]}],
            }
            config_path.write_text(json.dumps(config), encoding="utf-8")
            found = mdsite.discover_sources(config, config_path)
            self.assertEqual([item["relative"] for item in found], ["public/ok.md"])


if __name__ == "__main__":
    unittest.main()
