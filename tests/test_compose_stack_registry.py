"""Compose stack catalog (infra_compose_stacks) schema + Phase 3 orchestration contracts.

Catalog is SoT; builders and phase tasks consume it via filter_plugins/compose_stacks.py.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "PyYAML is required for compose stack registry tests (install ansible / PyYAML)"
    ) from exc

REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_06 = REPO_ROOT / "roles" / "06-enable-compose-systemd"
DEFAULTS = ROLE_06 / "defaults" / "main.yml"
BUILD_PROJECTS = ROLE_06 / "tasks" / "build_compose_systemd_projects.yaml"
BUILD_IMAGES = ROLE_06 / "tasks" / "build_compose_pre_pull_images.yaml"
RECONCILE = ROLE_06 / "tasks" / "reconcile.yaml"
COMPOSE_RECONCILE = ROLE_06 / "tasks" / "compose_reconcile.yaml"
PRE_PULL = ROLE_06 / "tasks" / "pre_pull_compose_images.yaml"
PLAYBOOK = REPO_ROOT / "playbooks" / "infra_hosts.yaml"
README = REPO_ROOT / "README.md"
ROLE_README = ROLE_06 / "README.md"

REQUIRED_STACK_KEYS = (
    "id",
    "role",
    "playbook_tag",
    "render_from",
    "start_group",
    "after",
    "image_var",
    "project_dir_var",
    "unit_name_var",
    "description",
    "up_extra",
    "enable_when",
    "skip_dedicated_unit_when",
    "post_start",
    "warm",
)

EXPECTED_STACK_IDS = (
    "bind",
    "ntp",
    "stepca",
    "registry",
    "registry_nginx",
    "pkg_repo_nginx",
    "helm_repo_nginx",
    "custom_nginx",
    "infra_stats",
)

CORE_STACK_IDS = frozenset({"bind", "ntp", "stepca"})
REGISTRY_STACK_IDS = frozenset(EXPECTED_STACK_IDS) - CORE_STACK_IDS
ALLOWED_START_GROUPS = frozenset({"core", "registry"})
PHASE_TASK_FILES = (
    "compose_render.yaml",
    "compose_pull.yaml",
    "compose_start_group.yaml",
    "compose_reconcile.yaml",
    "compose_run_post_start.yaml",
    "compose_run_pre_start.yaml",
    "compose_run_warm.yaml",
)
PHASE_TAGS = (
    "compose_render",
    "compose_pull",
    "compose_start_core",
    "compose_start_registry",
    "compose_reconcile",
)


def _load_stacks() -> list[dict[str, Any]]:
    data = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8")) or {}
    stacks = data.get("infra_compose_stacks")
    if not isinstance(stacks, list) or not stacks:
        raise AssertionError("infra_compose_stacks must be a non-empty list in role 06 defaults")
    return stacks


def _assert_no_cycle(stacks: list[dict[str, Any]]) -> None:
    ids = {s["id"] for s in stacks}
    edges: dict[str, list[str]] = {s["id"]: list(s.get("after") or []) for s in stacks}
    for sid, deps in edges.items():
        for dep in deps:
            if dep not in ids:
                raise AssertionError(f"stack {sid!r} after[] references unknown id {dep!r}")

    visiting: set[str] = set()
    done: set[str] = set()

    def dfs(node: str) -> None:
        if node in done:
            return
        if node in visiting:
            raise AssertionError(f"infra_compose_stacks after[] has a cycle involving {node!r}")
        visiting.add(node)
        for dep in edges[node]:
            dfs(dep)
        visiting.remove(node)
        done.add(node)

    for sid in edges:
        dfs(sid)


class ComposeStackRegistryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stacks = _load_stacks()
        cls.by_id = {s["id"]: s for s in cls.stacks}
        cls.projects_text = BUILD_PROJECTS.read_text(encoding="utf-8")
        cls.images_text = BUILD_IMAGES.read_text(encoding="utf-8")
        cls.reconcile_text = RECONCILE.read_text(encoding="utf-8")
        cls.compose_reconcile_text = COMPOSE_RECONCILE.read_text(encoding="utf-8")
        cls.pre_pull_text = PRE_PULL.read_text(encoding="utf-8")
        cls.playbook_text = PLAYBOOK.read_text(encoding="utf-8")
        cls.readme_text = README.read_text(encoding="utf-8")
        cls.role_readme_text = ROLE_README.read_text(encoding="utf-8")

    def test_catalog_files_exist(self) -> None:
        self.assertTrue(DEFAULTS.is_file())
        self.assertTrue(BUILD_PROJECTS.is_file())
        self.assertTrue(BUILD_IMAGES.is_file())
        self.assertTrue(ROLE_README.is_file())
        self.assertTrue((REPO_ROOT / "filter_plugins" / "compose_stacks.py").is_file())

    def test_schema_keys_and_types(self) -> None:
        for stack in self.stacks:
            missing = [k for k in REQUIRED_STACK_KEYS if k not in stack]
            self.assertEqual(missing, [], f"stack {stack.get('id')!r} missing keys: {missing}")
            self.assertIsInstance(stack["id"], str)
            self.assertIsInstance(stack["role"], str)
            self.assertIsInstance(stack["playbook_tag"], str)
            self.assertIsInstance(stack["render_from"], str)
            self.assertIsInstance(stack["start_group"], str)
            self.assertIsInstance(stack["after"], list)
            self.assertIsInstance(stack["image_var"], str)
            self.assertIsInstance(stack["project_dir_var"], str)
            self.assertIsInstance(stack["unit_name_var"], str)
            self.assertIsInstance(stack["description"], str)
            self.assertIsInstance(stack["up_extra"], str)
            self.assertIsInstance(stack["post_start"], list)
            self.assertIsInstance(stack["warm"], list)
            self.assertIsInstance(stack["enable_when"], dict)
            self.assertIsInstance(stack["enable_when"].get("all_true"), list)
            self.assertIsInstance(stack["skip_dedicated_unit_when"], dict)
            self.assertIsInstance(stack["skip_dedicated_unit_when"].get("all_true"), list)
            self.assertIn(stack["start_group"], ALLOWED_START_GROUPS)
            self.assertTrue(stack["id"], "empty stack id")
            self.assertTrue(
                stack["image_var"].endswith("_image") or stack["image_var"].endswith("_Image")
            )
            self.assertIn("compose_project_dir", stack["project_dir_var"])
            self.assertTrue(stack["unit_name_var"].startswith("compose_systemd_"))
            self.assertTrue(stack["unit_name_var"].endswith("_unit_name"))

    def test_expected_ids_order_and_uniqueness(self) -> None:
        ids = [s["id"] for s in self.stacks]
        self.assertEqual(tuple(ids), EXPECTED_STACK_IDS)
        self.assertEqual(len(ids), len(set(ids)))

        unit_vars = [s["unit_name_var"] for s in self.stacks]
        self.assertEqual(len(unit_vars), len(set(unit_vars)), unit_vars)

        roles = [s["role"] for s in self.stacks]
        self.assertEqual(len(roles), len(set(roles)), roles)

        image_vars = [s["image_var"] for s in self.stacks]
        self.assertEqual(len(image_vars), len(set(image_vars)), image_vars)

        project_vars = [s["project_dir_var"] for s in self.stacks]
        self.assertEqual(len(project_vars), len(set(project_vars)), project_vars)

        tags = [s["playbook_tag"] for s in self.stacks]
        self.assertEqual(len(tags), len(set(tags)), tags)

    def test_start_groups_partition(self) -> None:
        core = {s["id"] for s in self.stacks if s["start_group"] == "core"}
        registry = {s["id"] for s in self.stacks if s["start_group"] == "registry"}
        self.assertEqual(core, CORE_STACK_IDS)
        self.assertEqual(registry, REGISTRY_STACK_IDS)
        self.assertEqual(core | registry, set(EXPECTED_STACK_IDS))
        self.assertFalse(core & registry)

    def test_after_dag_acyclic_and_known(self) -> None:
        _assert_no_cycle(self.stacks)
        self.assertEqual(self.by_id["ntp"]["after"], ["bind"])
        self.assertEqual(self.by_id["registry_nginx"]["after"], ["registry"])
        self.assertEqual(self.by_id["bind"]["after"], [])
        self.assertEqual(self.by_id["stepca"]["after"], [])
        self.assertEqual(self.by_id["registry"]["after"], [])

    def test_roles_and_warm_hooks_exist(self) -> None:
        for stack in self.stacks:
            role_dir = REPO_ROOT / "roles" / stack["role"]
            self.assertTrue(role_dir.is_dir(), stack["role"])
            self.assertTrue((role_dir / "tasks" / "main.yaml").is_file(), stack["role"])
            render_path = role_dir / "tasks" / stack["render_from"]
            self.assertTrue(render_path.is_file(), f"{stack['id']}: missing {stack['render_from']}")
            main_text = (role_dir / "tasks" / "main.yaml").read_text(encoding="utf-8")
            self.assertIn(f"import_tasks: {stack['render_from']}", main_text, stack["id"])
            for warm in stack["warm"]:
                warm_path = role_dir / "tasks" / warm
                self.assertTrue(warm_path.is_file(), f"{stack['id']}: missing warm task {warm}")
            for post in stack.get("post_start") or []:
                post_path = role_dir / "tasks" / post
                self.assertTrue(post_path.is_file(), f"{stack['id']}: missing post_start {post}")
            bootstrap = stack.get("bootstrap_from")
            if bootstrap:
                self.assertTrue(
                    (role_dir / "tasks" / bootstrap).is_file(),
                    f"{stack['id']}: missing bootstrap {bootstrap}",
                )
                self.assertIn(f"import_tasks: {bootstrap}", main_text, stack["id"])
            self.assertEqual(stack["render_from"], "render.yaml")

    def test_render_tasks_forbid_pull_and_stack_start(self) -> None:
        """Phase 1 contract: render.yaml must not pull images or start compose stacks."""
        forbidden_substrings = (
            "pre_pull_compose_images.yaml",
            "warm_cache.yaml",
            "docker compose up",
        )
        unit_start_re = re.compile(
            r"name:\s*\"\{\{\s*compose_systemd_\w+_unit_name\s*\}\}\.service\".*?"
            r"state:\s*(started|restarted)",
            re.S,
        )
        for stack in self.stacks:
            render = (
                REPO_ROOT / "roles" / stack["role"] / "tasks" / stack["render_from"]
            ).read_text(encoding="utf-8")
            executable = "\n".join(
                line for line in render.splitlines() if not line.lstrip().startswith("#")
            )
            for needle in forbidden_substrings:
                self.assertNotIn(
                    needle,
                    executable,
                    f"{stack['id']} render contains {needle}",
                )
            self.assertIsNone(
                unit_start_re.search(executable),
                f"{stack['id']} render starts/restarts a compose systemd unit",
            )
            self.assertTrue(
                any("Phase 1 render" in line for line in render.splitlines()[:5]),
                f"{stack['id']} render missing Phase 1 header comment",
            )

    def test_tls_issue_deferred_when_stepca_unprovisioned(self) -> None:
        """Cold path: compose_render must not hard-fail before compose_start_core ACME."""
        for role in (
            "05-deploy-registry-compose",
            "08-deploy-pkg-repo-nginx-compose",
            "09-deploy-helm-repo-nginx-compose",
            "10-deploy-custom-nginx-compose",
            "13-deploy-infra-stats",
        ):
            render = (REPO_ROOT / "roles" / role / "tasks" / "render.yaml").read_text(
                encoding="utf-8"
            )
            executable = "\n".join(
                line for line in render.splitlines() if not line.lstrip().startswith("#")
            )
            self.assertIn("Defer", render, role)
            self.assertIn("import_tasks: issue_tls.yaml", executable, role)
            # Hard assert on provisioned marker must not sit in render unconditionally.
            self.assertNotRegex(
                executable,
                r"(?m)^- name: Require provisioned step-ca",
                role,
            )
        start_group = (ROLE_06 / "tasks" / "compose_start_group.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("compose_stacks_pre_start", start_group)
        self.assertIn("compose_stacks_for_render", start_group)
        self.assertIn("compose_topo_sort", start_group)
        # pre_start resolve must topo-sort (not catalog order alone).
        pre_start_resolve = start_group.split(
            "Resolve compose stacks for pre_start hooks", 1
        )[1].split("- name: Run pre_start hooks", 1)[0]
        self.assertIn("compose_topo_sort", pre_start_resolve)

        render_phase = (ROLE_06 / "tasks" / "compose_render.yaml").read_text(
            encoding="utf-8"
        )
        render_resolve = render_phase.split(
            "Resolve and topo-sort compose stacks for render", 1
        )[1].split("- name: Render enabled compose stack files", 1)[0]
        self.assertIn("compose_stacks_for_render", render_resolve)
        self.assertIn("compose_topo_sort", render_resolve)

        infra_stats_after = self.by_id["infra_stats"].get("after") or []
        for dep in (
            "registry",
            "registry_nginx",
            "pkg_repo_nginx",
            "helm_repo_nginx",
            "custom_nginx",
        ):
            self.assertIn(dep, infra_stats_after, dep)

    def test_bind_ntp_post_start_and_stepca_bootstrap(self) -> None:
        self.assertEqual(self.by_id["bind"]["post_start"], ["post_start.yaml"])
        self.assertEqual(self.by_id["ntp"]["post_start"], ["post_start.yaml"])
        self.assertEqual(self.by_id["ntp"].get("pre_start"), ["pre_start.yaml"])
        self.assertEqual(self.by_id["stepca"].get("bootstrap_from"), "bootstrap.yaml")
        for sid in ("registry", "pkg_repo_nginx", "helm_repo_nginx", "custom_nginx", "infra_stats"):
            self.assertEqual(self.by_id[sid].get("pre_start"), ["pre_start.yaml"], sid)
            role = self.by_id[sid]["role"]
            pre = REPO_ROOT / "roles" / role / "tasks" / "pre_start.yaml"
            issue = REPO_ROOT / "roles" / role / "tasks" / "issue_tls.yaml"
            self.assertTrue(pre.is_file(), sid)
            self.assertTrue(issue.is_file(), sid)
            self.assertIn("issue_tls.yaml", pre.read_text(encoding="utf-8"), sid)
        bind_post = (
            REPO_ROOT / "roles" / "03-deploy-bind-compose" / "tasks" / "post_start.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("configure_infra_resolver.yaml", bind_post)
        ntp_post = (
            REPO_ROOT / "roles" / "12-deploy-ntp-compose" / "tasks" / "post_start.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("chronyc", ntp_post)
        ntp_pre = (
            REPO_ROOT / "roles" / "12-deploy-ntp-compose" / "tasks" / "pre_start.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("UDP/123", ntp_pre)
        self.assertIn("masked: true", ntp_pre)
        ntp_td = (
            REPO_ROOT / "roles" / "12-deploy-ntp-compose" / "tasks" / "teardown.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("masked: false", ntp_td)
        bootstrap = (
            REPO_ROOT / "roles" / "04-deploy-stepca-compose" / "tasks" / "bootstrap.yaml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("pre_pull_compose_images.yaml", bootstrap)
        self.assertIn("state: started", bootstrap)
        self.assertIn("mark_compose_pending_restart.yaml", bootstrap)

    def test_phase5_thin_main_no_per_role_pre_pull(self) -> None:
        """Phase 5: deploy-role main.yaml is render-only (+ stepca bootstrap); no pre-pull."""
        for stack in self.stacks:
            main_text = (
                REPO_ROOT / "roles" / stack["role"] / "tasks" / "main.yaml"
            ).read_text(encoding="utf-8")
            executable = "\n".join(
                line for line in main_text.splitlines() if not line.lstrip().startswith("#")
            )
            self.assertNotIn("pre_pull_compose_images.yaml", executable, stack["id"])
            self.assertNotIn("import_tasks: apply_runtime.yaml", executable, stack["id"])
            self.assertIn(f"import_tasks: {stack['render_from']}", executable, stack["id"])
            if stack.get("bootstrap_from"):
                self.assertIn(f"import_tasks: {stack['bootstrap_from']}", executable, stack["id"])
            else:
                # Thin mains: only render import (no start/warm/post_start).
                self.assertNotIn("import_tasks: post_start.yaml", executable, stack["id"])
                self.assertNotIn("import_tasks: pre_start.yaml", executable, stack["id"])
                self.assertNotIn("import_tasks: warm_cache.yaml", executable, stack["id"])
                self.assertEqual(
                    executable.count("import_tasks:"),
                    1,
                    f"{stack['id']} main should only import render",
                )

        for role in (
            "07-deploy-registry-nginx-compose",
            "08-deploy-pkg-repo-nginx-compose",
            "09-deploy-helm-repo-nginx-compose",
            "10-deploy-custom-nginx-compose",
        ):
            runtime = (
                REPO_ROOT / "roles" / role / "tasks" / "apply_runtime.yaml"
            ).read_text(encoding="utf-8")
            self.assertNotIn("pre_pull_compose_images.yaml", runtime, role)

        pkg_render = (
            REPO_ROOT / "roles" / "08-deploy-pkg-repo-nginx-compose" / "tasks" / "render.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("pkg_repo_cache_warm_pending", pkg_render)

    def test_playbook_tags_present(self) -> None:
        for stack in self.stacks:
            self.assertIn(stack["playbook_tag"], self.playbook_text, stack["id"])

    def test_builders_wired_to_catalog_filters(self) -> None:
        for label, text in (
            ("projects", self.projects_text),
            ("images", self.images_text),
        ):
            executable = "\n".join(
                line for line in text.splitlines() if not line.lstrip().startswith("#")
            )
            self.assertIn("infra_compose_stacks", executable, label)
            self.assertIn("compose_stacks_to_", executable, label)

    def test_phase_task_files_and_playbook_opt_in_tags(self) -> None:
        for name in PHASE_TASK_FILES:
            self.assertTrue((ROLE_06 / "tasks" / name).is_file(), name)
        for tag in PHASE_TAGS:
            self.assertIn(tag, self.playbook_text, tag)
        self.assertIn("ansible_run_tags", self.playbook_text)
        self.assertIn("tasks_from: compose_render.yaml", self.playbook_text)
        self.assertIn("tasks_from: compose_pull.yaml", self.playbook_text)
        self.assertIn("tasks_from: compose_start_group.yaml", self.playbook_text)

    def test_reconcile_is_slim_no_full_pre_pull(self) -> None:
        for text in (self.reconcile_text, self.compose_reconcile_text):
            executable = "\n".join(
                line for line in text.splitlines() if not line.lstrip().startswith("#")
            )
            self.assertNotIn("build_compose_pre_pull_images.yaml", executable)
            self.assertNotIn("pre_pull_compose_images.yaml", executable)
        self.assertIn("compose_reconcile.yaml", self.reconcile_text)
        self.assertIn("compose_stacks_pending_restart", self.compose_reconcile_text)

    def test_pre_pull_supports_skip_if_present(self) -> None:
        self.assertIn("docker image inspect", self.pre_pull_text)
        self.assertIn("compose_pull_force", self.pre_pull_text)
        self.assertIn("compose_pull_parallel", self.pre_pull_text)
        self.assertIn("async:", self.pre_pull_text)
        self.assertIn("Assert parallel compose image pulls succeeded", self.pre_pull_text)

    def test_phase6_parallel_pull_and_timing_defaults(self) -> None:
        defaults = (ROLE_06 / "defaults" / "main.yml").read_text(encoding="utf-8")
        self.assertRegex(defaults, r"(?m)^compose_pull_parallel:\s*true\s*$")
        self.assertRegex(defaults, r"(?m)^compose_timing_enabled:\s*true\s*$")
        for name in (
            "compose_render.yaml",
            "compose_pull.yaml",
            "compose_start_group.yaml",
            "compose_reconcile.yaml",
        ):
            text = (ROLE_06 / "tasks" / name).read_text(encoding="utf-8")
            self.assertIn("compose_timing_begin.yaml", text, name)
            self.assertIn("compose_timing_end.yaml", text, name)
        playbook = (REPO_ROOT / "playbooks" / "infra_hosts.yaml").read_text(encoding="utf-8")
        self.assertIn("compose_timing_phase: 11_sync_infra_cache_pull", playbook)
        self.assertIn("compose_timing_phase: 11_sync_infra_cache_push", playbook)
        self.assertIn("compose_timing_phase: 14_infra_cache_seed_load", playbook)
        self.assertIn("compose_timing_phase: 14_infra_cache_seed_publish", playbook)
        end = (ROLE_06 / "tasks" / "compose_timing_end.yaml").read_text(encoding="utf-8")
        self.assertIn("atlas_infra_edge_timing", end)

    def test_shared_skip_semantics_for_sidecar_nginx(self) -> None:
        for sid, shared_flag in (
            ("pkg_repo_nginx", "pkg_repo_nginx_shared_with_registry"),
            ("helm_repo_nginx", "helm_repo_nginx_shared_with_registry"),
            ("custom_nginx", "custom_nginx_shared_with_registry"),
            ("infra_stats", "infra_stats_shared_with_registry"),
        ):
            skip = self.by_id[sid]["skip_dedicated_unit_when"]["all_true"]
            self.assertEqual(skip, [shared_flag, "setup_registry_nginx"], sid)

        for sid in ("bind", "ntp", "stepca", "registry", "registry_nginx"):
            self.assertEqual(self.by_id[sid]["skip_dedicated_unit_when"]["all_true"], [], sid)

    def test_docs_describe_contract(self) -> None:
        for text in (self.readme_text, self.role_readme_text):
            self.assertIn("infra_compose_stacks", text)
            self.assertIn("start_group", text)
            self.assertIn("render", text.lower())
            self.assertIn("registry", text.lower())
            self.assertIn("cache pull", text.lower())

        self.assertIn("test_compose_stack_registry.py", self.readme_text)
        self.assertIn("compose_render", self.readme_text)
        self.assertIn("compose_start_core", self.readme_text)
        self.assertIn("compose_start_registry", self.readme_text)
        catalog = (REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.yml").read_text(encoding="utf-8")
        self.assertIn("infra_compose_stacks", catalog)


if __name__ == "__main__":
    unittest.main()
