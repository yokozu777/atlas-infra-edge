"""Layout tests for pkg_repo filter in atlas-infra-edge."""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class InfraEdgePkgRepoFilterTest(unittest.TestCase):
    def test_pgdg_slugs_and_public_urls(self) -> None:
        pkg_repo = (REPO_ROOT / "filter_plugins" / "pkg_repo.py").read_text(encoding="utf-8")
        self.assertIn('"pgdg-apt": "https://apt.postgresql.org/pub/repos/apt"', pkg_repo)
        self.assertIn(
            '"pgdg-yum": "https://download.postgresql.org/pub/repos/yum"',
            pkg_repo,
        )

    def test_gitlab_runner_slugs_and_public_urls(self) -> None:
        pkg_repo = (REPO_ROOT / "filter_plugins" / "pkg_repo.py").read_text(encoding="utf-8")
        self.assertIn(
            '"gitlab-runner-ubuntu": "https://packages.gitlab.com/runner/gitlab-runner/ubuntu"',
            pkg_repo,
        )
        self.assertIn(
            '"gitlab-runner-debian": "https://packages.gitlab.com/runner/gitlab-runner/debian"',
            pkg_repo,
        )
        self.assertIn(
            '"gitlab-runner-el": "https://packages.gitlab.com/runner/gitlab-runner/el/9/x86_64"',
            pkg_repo,
        )


if __name__ == "__main__":
    unittest.main()
