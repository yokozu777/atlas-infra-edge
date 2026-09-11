"""Phase 3: PGDG upstreams + infra-local pkg-repo nginx gate."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG = REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.yml"
PULL_MODES = REPO_ROOT / "roles" / "01_validate_vars" / "tasks" / "pull_modes.yml"
WARM_SH = (
    REPO_ROOT
    / "roles"
    / "08-deploy-pkg-repo-nginx-compose"
    / "templates"
    / "warm-pkg-repo-cache.sh.j2"
)
WARM_TASKS = (
    REPO_ROOT / "roles" / "08-deploy-pkg-repo-nginx-compose" / "tasks" / "warm_cache.yaml"
)
DOCS = REPO_ROOT / "docs" / "pkg-repos.md"


def _static_upstreams(text: str) -> dict[str, dict[str, str]]:
    m = re.search(
        r"^pkg_repo_upstreams:\n(.*?)(?=\n# =+\n|\nhelm_repo_upstreams:)",
        text,
        re.S | re.M,
    )
    if not m:
        raise AssertionError("pkg_repo_upstreams block missing")
    out: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    skip = False
    for line in m.group(1).splitlines():
        if re.match(r"\s+- slug:", line):
            skip = "{{" in line
            current = None
            if skip:
                continue
            sm = re.match(r'\s+- slug:\s*"?([^"#]+?)"?\s*$', line)
            if not sm:
                skip = True
                continue
            slug = sm.group(1).strip().strip('"')
            current = {}
            out[slug] = current
            continue
        if skip or current is None:
            continue
        um = re.match(r'\s+upstream_url:\s*"([^"]+)"\s*$', line)
        if um:
            current["upstream_url"] = um.group(1)
            continue
        hm = re.match(r"\s+upstream_host:\s*(\S+)\s*$", line)
        if hm:
            current["upstream_host"] = hm.group(1)
    return out


class PkgReposPhase3InfraTest(unittest.TestCase):
    def test_pgdg_upstreams_present(self) -> None:
        catalog = CATALOG.read_text(encoding="utf-8")
        upstreams = _static_upstreams(catalog)
        self.assertIn("pgdg-apt", upstreams)
        self.assertEqual(
            upstreams["pgdg-apt"]["upstream_url"],
            "https://apt.postgresql.org/pub/repos/apt",
        )
        self.assertEqual(upstreams["pgdg-apt"]["upstream_host"], "apt.postgresql.org")
        self.assertIn("pgdg-yum", upstreams)
        self.assertEqual(
            upstreams["pgdg-yum"]["upstream_url"],
            "https://download.postgresql.org/pub/repos/yum",
        )
        self.assertEqual(upstreams["pgdg-yum"]["upstream_host"], "download.postgresql.org")
        self.assertIn("enable_repo_pgdg_apt: true", catalog)
        self.assertIn("enable_repo_pgdg_yum: true", catalog)

    def test_mirror_gate_is_setup_pkg_repo_nginx(self) -> None:
        catalog = CATALOG.read_text(encoding="utf-8")
        self.assertIn('setup_apt_rpm_nginx: "{{ setup_pkg_repo_nginx | bool }}"', catalog)
        self.assertNotIn(
            "setup_apt_rpm_nginx: \"{{ use_internal_rpm_apt_repo == 'nginx' and setup_pkg_repo_nginx }}\"",
            catalog,
        )
        self.assertIn("install_managed_pkg_repos: false", catalog)

        pull = PULL_MODES.read_text(encoding="utf-8")
        self.assertIn("setup_apt_rpm_nginx must equal setup_pkg_repo_nginx", pull)
        self.assertIn("when setup_pkg_repo_nginx=true", pull)
        self.assertNotIn(
            "(use_internal_rpm_apt_repo == 'nginx' and setup_pkg_repo_nginx=true)",
            pull,
        )

    def test_warm_covers_pgdg(self) -> None:
        warm = WARM_SH.read_text(encoding="utf-8")
        self.assertIn("warm_pgdg_apt", warm)
        self.assertIn("warm_pgdg_yum", warm)
        self.assertIn("pgdg-apt)", warm)
        self.assertIn("pgdg-yum)", warm)
        self.assertIn("-pgdg/InRelease", warm)
        tasks = WARM_TASKS.read_text(encoding="utf-8")
        self.assertIn("enable_repo_pgdg", tasks)
        self.assertIn("pgdg-apt", tasks)

    def test_docs_phase3(self) -> None:
        docs = DOCS.read_text(encoding="utf-8")
        self.assertIn("Phase 3", docs)
        self.assertIn("pgdg-apt", docs)
        self.assertIn("setup_pkg_repo_nginx", docs)

    def test_gitlab_runner_upstreams_present(self) -> None:
        catalog = CATALOG.read_text(encoding="utf-8")
        upstreams = _static_upstreams(catalog)
        self.assertEqual(
            upstreams["gitlab-runner-ubuntu"]["upstream_url"],
            "https://packages.gitlab.com/runner/gitlab-runner/ubuntu",
        )
        self.assertEqual(
            upstreams["gitlab-runner-ubuntu"]["upstream_host"],
            "packages.gitlab.com",
        )
        self.assertEqual(
            upstreams["gitlab-runner-debian"]["upstream_url"],
            "https://packages.gitlab.com/runner/gitlab-runner/debian",
        )
        self.assertEqual(
            upstreams["gitlab-runner-el"]["upstream_url"],
            "https://packages.gitlab.com/runner/gitlab-runner/el/9/x86_64",
        )
        self.assertIn("enable_repo_gitlab_runner_ubuntu: true", catalog)
        self.assertIn("enable_repo_gitlab_runner_debian: true", catalog)
        self.assertIn("enable_repo_gitlab_runner_el: true", catalog)
        warm = WARM_SH.read_text(encoding="utf-8")
        self.assertIn("gitlab-runner-ubuntu)", warm)
        self.assertIn("gitlab-runner-debian)", warm)
        docs = DOCS.read_text(encoding="utf-8")
        self.assertIn("gitlab-runner-ubuntu", docs)


if __name__ == "__main__":
    unittest.main()
