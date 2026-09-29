import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
IBS_DOCUMENT = "2026-09-25-IBS-gastroenterology-appointment-prep.md"


class DockerPackagingTests(unittest.TestCase):
    def test_docker_config_uses_exact_content_allowlist(self):
        config = json.loads((ROOT / "site.docker.json").read_text(encoding="utf-8"))
        self.assertEqual(config["output_dir"], "dist")
        self.assertEqual(
            config["sources"],
            [{"root": "content", "include": [IBS_DOCUMENT], "exclude": []}],
        )
        self.assertTrue((ROOT / "content" / IBS_DOCUMENT).is_file())

    def test_dockerfile_is_multistage_and_never_broad_copies_context(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertGreaterEqual(len(re.findall(r"^FROM ", dockerfile, re.MULTILINE)), 2)
        self.assertNotRegex(dockerfile, r"(?m)^COPY\s+(?:--\S+\s+)*\.\s")
        self.assertIn("COPY content/ ./content/", dockerfile)
        self.assertIn("COPY --from=builder", dockerfile)
        self.assertIn("USER 101:101", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)

    def test_compose_has_private_and_hardened_defaults(self):
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        for expected in (
            "${BIND_ADDRESS:-127.0.0.1}:${PORT:-8080}:8080",
            "read_only: true",
            'user: "101:101"',
            "no-new-privileges:true",
            "cap_drop:",
            "restart: unless-stopped",
            "healthcheck:",
        ):
            self.assertIn(expected, compose)

    def test_context_and_git_ignores_protect_sensitive_material(self):
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertRegex(dockerignore, r"(?m)^\*\*$")
        self.assertNotIn("!README.md", dockerignore)
        self.assertIn("!content/*.md", dockerignore)

        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("content/**", gitignore)
        self.assertIn("!content/.gitkeep", gitignore)
        self.assertIn("dist/", gitignore)

    def test_nginx_sets_static_security_and_no_store_headers(self):
        nginx = (ROOT / "nginx.conf").read_text(encoding="utf-8")
        for expected in (
            "listen 8080",
            'Cache-Control "private, no-store, max-age=0"',
            "Content-Security-Policy",
            'X-Content-Type-Options "nosniff"',
            'X-Frame-Options "DENY"',
            "location = /healthz",
        ):
            self.assertIn(expected, nginx)


if __name__ == "__main__":
    unittest.main()
