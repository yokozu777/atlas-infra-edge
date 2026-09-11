"""Unit tests for filter_plugins/compose_stacks.py (Phase 2)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_compose_stacks():
    path = REPO_ROOT / "filter_plugins" / "compose_stacks.py"
    spec = importlib.util.spec_from_file_location("compose_stacks", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


COMPOSE = _load_compose_stacks()

_CATALOG = [
    {
        "id": "bind",
        "start_group": "core",
        "after": [],
        "image_var": "bind_image",
        "project_dir_var": "bind_compose_project_dir",
        "unit_name_var": "compose_systemd_bind_unit_name",
        "description": "BIND9 DNS",
        "up_extra": "",
        "enable_when": {"all_true": ["setup_bind"]},
        "skip_dedicated_unit_when": {"all_true": []},
    },
    {
        "id": "ntp",
        "start_group": "core",
        "after": ["bind"],
        "image_var": "ntp_image",
        "project_dir_var": "ntp_compose_project_dir",
        "unit_name_var": "compose_systemd_ntp_unit_name",
        "description": "NTP",
        "up_extra": "",
        "enable_when": {"all_true": ["setup_ntp"]},
        "skip_dedicated_unit_when": {"all_true": []},
    },
    {
        "id": "registry",
        "start_group": "registry",
        "after": [],
        "image_var": "registry_image",
        "project_dir_var": "registry_compose_project_dir",
        "unit_name_var": "compose_systemd_registry_unit_name",
        "description": "Registry",
        "up_extra": "--remove-orphans",
        "enable_when": {"all_true": ["setup_registry"]},
        "skip_dedicated_unit_when": {"all_true": []},
    },
    {
        "id": "registry_nginx",
        "start_group": "registry",
        "after": ["registry"],
        "image_var": "registry_nginx_image",
        "project_dir_var": "registry_nginx_compose_project_dir",
        "unit_name_var": "compose_systemd_registry_nginx_unit_name",
        "description": "Registry nginx",
        "up_extra": "--remove-orphans",
        "enable_when": {"all_true": ["setup_registry", "setup_registry_nginx"]},
        "skip_dedicated_unit_when": {"all_true": []},
    },
    {
        "id": "pkg_repo_nginx",
        "start_group": "registry",
        "after": [],
        "image_var": "pkg_repo_nginx_image",
        "project_dir_var": "pkg_repo_nginx_compose_project_dir",
        "unit_name_var": "compose_systemd_pkg_repo_nginx_unit_name",
        "description": "pkg nginx",
        "up_extra": "--remove-orphans",
        "enable_when": {"all_true": ["setup_apt_rpm_nginx"]},
        "skip_dedicated_unit_when": {
            "all_true": ["pkg_repo_nginx_shared_with_registry", "setup_registry_nginx"]
        },
    },
]


class ComposeStacksFilterTest(unittest.TestCase):
    def test_gates_and_shared_skip(self) -> None:
        variables = {
            "setup_bind": True,
            "setup_ntp": False,
            "setup_registry": True,
            "setup_registry_nginx": True,
            "setup_apt_rpm_nginx": True,
            "pkg_repo_nginx_shared_with_registry": True,
        }
        render_ids = [s["id"] for s in COMPOSE.compose_stacks_for_render(_CATALOG, variables)]
        self.assertEqual(render_ids, ["bind", "registry", "registry_nginx", "pkg_repo_nginx"])
        unit_ids = [s["id"] for s in COMPOSE.compose_stacks_for_units(_CATALOG, variables)]
        self.assertEqual(unit_ids, ["bind", "registry", "registry_nginx"])
        self.assertNotIn("pkg_repo_nginx", unit_ids)

    def test_topo_sort_honours_after(self) -> None:
        variables = {
            "setup_bind": True,
            "setup_ntp": True,
            "setup_registry": True,
            "setup_registry_nginx": True,
            "setup_apt_rpm_nginx": False,
            "pkg_repo_nginx_shared_with_registry": True,
        }
        core = COMPOSE.compose_stacks_in_group(_CATALOG, variables, "core")
        sorted_core = COMPOSE.compose_topo_sort(core)
        self.assertEqual([s["id"] for s in sorted_core], ["bind", "ntp"])

        registry = COMPOSE.compose_stacks_in_group(_CATALOG, variables, "registry")
        sorted_reg = COMPOSE.compose_topo_sort(registry)
        self.assertEqual([s["id"] for s in sorted_reg], ["registry", "registry_nginx"])

    def test_topo_sort_detects_cycle(self) -> None:
        cyclic = [
            {"id": "a", "after": ["b"]},
            {"id": "b", "after": ["a"]},
        ]
        with self.assertRaises(ValueError):
            COMPOSE.compose_topo_sort(cyclic)

    def test_projects_and_images(self) -> None:
        variables = {
            "setup_bind": True,
            "setup_ntp": True,
            "setup_registry": False,
            "setup_registry_nginx": False,
            "setup_apt_rpm_nginx": False,
            "pkg_repo_nginx_shared_with_registry": True,
            "bind_image": "ubuntu/bind9:edge",
            "ntp_image": "cturra/ntp:latest",
            "bind_compose_project_dir": "/opt/bind-compose",
            "ntp_compose_project_dir": "/opt/ntp-compose",
            "compose_systemd_bind_unit_name": "bind-compose",
            "compose_systemd_ntp_unit_name": "ntp-compose",
        }
        projects = COMPOSE.compose_stacks_to_projects(_CATALOG, variables)
        self.assertEqual(
            [(p["unit_name"], p["after_units"]) for p in projects],
            [("bind-compose", ""), ("ntp-compose", "bind-compose.service")],
        )
        images = COMPOSE.compose_stacks_to_images(_CATALOG, variables)
        self.assertEqual(images, ["ubuntu/bind9:edge", "cturra/ntp:latest"])

    def test_shared_pkg_skips_dedicated_image(self) -> None:
        variables = {
            "setup_bind": False,
            "setup_ntp": False,
            "setup_registry": True,
            "setup_registry_nginx": True,
            "setup_apt_rpm_nginx": True,
            "pkg_repo_nginx_shared_with_registry": True,
            "registry_image": "registry:3",
            "registry_nginx_image": "nginx:alpine",
            "pkg_repo_nginx_image": "nginx:alpine",
            "registry_compose_project_dir": "/opt/registry",
            "registry_nginx_compose_project_dir": "/opt/registry-nginx",
            "pkg_repo_nginx_compose_project_dir": "/opt/pkg",
            "compose_systemd_registry_unit_name": "registry-compose",
            "compose_systemd_registry_nginx_unit_name": "registry-nginx-compose",
            "compose_systemd_pkg_repo_nginx_unit_name": "pkg-repo-nginx-compose",
        }
        images = COMPOSE.compose_stacks_to_images(_CATALOG, variables)
        self.assertEqual(images, ["registry:3", "nginx:alpine"])
        projects = COMPOSE.compose_stacks_to_projects(_CATALOG, variables)
        self.assertEqual([p["id"] for p in projects], ["registry", "registry_nginx"])


if __name__ == "__main__":
    unittest.main()
