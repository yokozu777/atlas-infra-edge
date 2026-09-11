"""Infra-edge repo layout / hygiene / fingerprint tests (publish step 2)."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_PRODUCT_SCAN_ROOTS = (
    REPO_ROOT / "roles",
    REPO_ROOT / "playbooks",
    REPO_ROOT / "group_vars",
    REPO_ROOT / "examples",
    REPO_ROOT / "host_vars",
    REPO_ROOT / "filter_plugins",
    REPO_ROOT / "inventory-example.yml",
    REPO_ROOT / "run.sh",
    REPO_ROOT / "ansible.cfg",
    REPO_ROOT / "requirements.yml",
    REPO_ROOT / "README.md",
)
_PRODUCT_SCAN_SUFFIXES = {".yml", ".yaml", ".j2", ".sh", ".cfg", ".md", ".py", ".toml"}
_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")

_EXPECTED_ROLES = (
    "00_ensure_workspace",
    "01_validate_vars",
    "00-bootstrap-infra-repos",
    "01-install-docker-engine",
    "02-configure-docker-daemon",
    "03-deploy-bind-compose",
    "04-deploy-stepca-compose",
    "05-deploy-registry-compose",
    "06-enable-compose-systemd",
    "07-deploy-registry-nginx-compose",
    "08-deploy-pkg-repo-nginx-compose",
    "09-deploy-helm-repo-nginx-compose",
    "10-deploy-custom-nginx-compose",
    "11-sync-infra-cache",
    "12-deploy-ntp-compose",
    "13-deploy-infra-stats",
    "14-infra-cache-seed",
)


def _scan_product_sources_for(
    needles: tuple[str, ...],
    *,
    case_sensitive: bool = False,
) -> list[str]:
    hits: list[str] = []
    for root in _PRODUCT_SCAN_ROOTS:
        if not root.exists():
            continue
        paths = [root] if root.is_file() else root.rglob("*")
        for path in paths:
            if not path.is_file():
                continue
            if path.suffix.lower() not in _PRODUCT_SCAN_SUFFIXES and path.name != "run.sh":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            haystack = text if case_sensitive else text.lower()
            for needle in needles:
                probe = needle if case_sensitive else needle.lower()
                if probe in haystack:
                    hits.append(f"{path.relative_to(REPO_ROOT)}:{needle}")
    return hits


class InfraEdgeLayoutTest(unittest.TestCase):
    def test_license_and_security_exist(self) -> None:
        self.assertTrue((REPO_ROOT / "LICENSE").is_file())
        self.assertTrue((REPO_ROOT / "SECURITY.md").is_file())
        self.assertTrue((REPO_ROOT / ".gitignore").is_file())
        self.assertTrue((REPO_ROOT / ".dockerignore").is_file())

    def test_gitignore_covers_inventory_and_workspace(self) -> None:
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        for needle in ("inventory.yml", "workspace/", "secrets.yml", "!roles/**/tasks/secrets.yml", "*.vault", "__pycache__/"):
            self.assertIn(needle, text)
        dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn("!roles/**/tasks/secrets.yml", dockerignore)

    def test_standalone_entrypoints(self) -> None:
        run_sh = REPO_ROOT / "run.sh"
        self.assertTrue(run_sh.is_file())
        self.assertTrue(run_sh.stat().st_mode & 0o111, "run.sh must be executable")
        self.assertTrue((REPO_ROOT / "inventory-example.yml").is_file())
        self.assertTrue((REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.yml").is_file())
        self.assertTrue((REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.secrets.yml").is_file())
        self.assertTrue((REPO_ROOT / "group_vars" / "all").is_dir())
        self.assertFalse((REPO_ROOT / "group_vars" / "all.yml").exists())
        self.assertFalse((REPO_ROOT / "group_vars" / "all" / "standalone.example.yml").exists())
        self.assertTrue((REPO_ROOT / "requirements.yml").is_file())
        self.assertTrue((REPO_ROOT / "examples" / "secrets.example.yml").is_file())
        self.assertTrue((REPO_ROOT / "host_vars" / "example.yml").is_file())

        catalog = (REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.yml").read_text(encoding="utf-8")
        secrets_overlay = (REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.secrets.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("REQUIRED", catalog)
        self.assertIn("OPTIONAL", catalog)
        self.assertIn("use_internal_rpm_apt_repo: none", catalog)
        self.assertIn("use_internal_docker_registry: none", catalog)
        self.assertNotIn("bind_apex_tsig_secret:", catalog)
        self.assertIn("bind_apex_tsig_secret:", secrets_overlay)
        self.assertIn("stepca_init_password:", secrets_overlay)
        self.assertIn("CHANGEME", secrets_overlay)
        self.assertIn("nginx_cache_sync_skip_if_fresh: false", catalog)
        self.assertIn("nginx_cache_sync_fresh_max_age_hours: 24", catalog)
        self.assertIn("infra_cache_seed_publish_enabled: false", catalog)
        self.assertIn("infra_cache_seed_load_enabled: false", catalog)
        self.assertNotIn("infra_cache_seed_publish_registry_password:", catalog)
        self.assertNotIn("infra_cache_seed_load_registry_password:", catalog)
        self.assertIn("infra_cache_seed_publish_registry_user:", secrets_overlay)
        self.assertIn("infra_cache_seed_load_registry_password:", secrets_overlay)
        self.assertIn("cluster_workspace_root:", catalog)
        self.assertIn("CLUSTER_WORKSPACE_ID", catalog)
        self.assertIn("CLUSTER_WORKSPACE_PARENT", catalog)
        self.assertIn("CLUSTER_WORKSPACE_ROOT", catalog)
        self.assertIn("infra_bootstrap_repo_state_dir: /var/lib/atlas-infra", catalog)
        self.assertNotIn("/var/lib/mxhash", catalog)
        self.assertIn("infra_platform_hosts: infra_platform", catalog)
        self.assertIn("groups[infra_platform_hosts]", catalog)
        self.assertNotIn("groups['infra_platform']", catalog)

        inventory = (REPO_ROOT / "inventory-example.yml").read_text(encoding="utf-8")
        self.assertIn("infra_platform:", inventory)
        self.assertIn("hostname:", inventory)
        self.assertIn("example.com", inventory)
        self.assertIn("infra_platform_hosts", inventory)

        run_text = run_sh.read_text(encoding="utf-8")
        self.assertIn("playbooks/infra_hosts.yaml", run_text)
        self.assertIn("CLUSTER_WORKSPACE_ROOT", run_text)
        self.assertIn("CLUSTER_WORKSPACE_PARENT", run_text)
        self.assertIn("EXTRA_VARS_FILE", run_text)
        self.assertIn("inventory-example.yml", run_text)

        secrets = (REPO_ROOT / "examples" / "secrets.example.yml").read_text(encoding="utf-8")
        self.assertIn("CHANGEME", secrets)
        self.assertIn("bind_apex_tsig_secret", secrets)
        self.assertIn("stepca_init_password", secrets)
        self.assertNotIn("mxhash", secrets.lower())
        self.assertNotIn("Welcomeback", secrets)

    def test_readme_quickstart_uses_run_sh(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Quickstart", readme)
        self.assertIn("./run.sh", readme)
        self.assertIn("group_vars/all/atlas-infra-edge.yml", readme)
        self.assertIn("inventory-example.yml", readme)
        self.assertIn("playbooks/infra_hosts.yaml", readme)
        self.assertIn("--tags 00_ensure_workspace", readme)
        self.assertIn("--tags 01_validate_vars", readme)
        self.assertIn("--tags 01_install_docker_engine", readme)
        self.assertNotIn("standalone.example.yml", readme)
        self.assertNotIn("gitea.", readme.lower())
        self.assertNotIn("mxhash", readme.lower())
        self.assertNotIn("clusterctl", readme)
        self.assertNotIn("./cluster ", readme)
        self.assertNotIn("./cluster\n", readme)
        self.assertIn("SECURITY.md", readme)
        self.assertIn("LICENSE", readme)

    def test_readme_is_standalone_first(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("./run.sh", readme)
        self.assertIn("## Quickstart", readme)
        self.assertIn("group_vars/all/atlas-infra-edge.yml", readme)
        self.assertIn("## Compatibility", readme)
        self.assertIn("## Architecture (role order)", readme)
        self.assertIn("## Feature gates and pull modes", readme)
        self.assertIn("## Compose stack catalog", readme)
        self.assertIn("## Greenfield checklist", readme)
        self.assertIn("## Troubleshooting", readme)
        self.assertIn("## Testing / CI", readme)
        self.assertIn("## Project structure", readme)
        self.assertIn("## Integrations", readme)
        self.assertIn("## Security", readme)
        self.assertIn("## Contributing", readme)
        self.assertIn("playbooks/infra_hosts.yaml", readme)
        self.assertIn("infra_platform_hosts", readme)
        self.assertIn("use_internal_rpm_apt_repo", readme)
        self.assertIn("infra_platform", readme)
        self.assertIn("infra_platform_hosts", readme)
        self.assertIn("my_infra_nodes", readme)
        self.assertIn("01_validate_vars", readme)
        self.assertIn("00_ensure_workspace", readme)
        self.assertIn("test_infra_edge_layout.py", readme)
        self.assertIn("test_compose_stack_registry.py", readme)
        self.assertIn("check-no-hardcoded-domains.sh", readme)
        self.assertIn("./tests/run_ci.sh", readme)
        self.assertIn(".github/workflows/ci.yml", readme)
        self.assertIn("ansible-lint", readme)
        self.assertIn("CLUSTER_WORKSPACE_PARENT", readme)
        self.assertNotIn("clusterctl", readme)
        self.assertNotIn("./cluster ", readme)
        self.assertNotIn("./cluster\n", readme)
        self.assertNotIn("gitea.", readme.lower())
        self.assertNotIn("mxhash", readme.lower())
        quick = readme.index("## Quickstart")
        integ = readme.index("## Integrations")
        self.assertLess(quick, integ)
        for earlier, later in (
            ("## Compatibility", "## Quickstart"),
            ("## Quickstart", "## Architecture (role order)"),
            ("## Architecture (role order)", "## Feature gates and pull modes"),
            ("## Feature gates and pull modes", "## Greenfield checklist"),
            ("## Greenfield checklist", "## Troubleshooting"),
            ("## Troubleshooting", "## Testing / CI"),
            ("## Testing / CI", "## Project structure"),
            ("## Project structure", "## Integrations"),
            ("## Integrations", "## Security"),
            ("## Security", "## Contributing"),
        ):
            self.assertLess(readme.index(earlier), readme.index(later), f"{earlier} before {later}")

    def test_readme_has_no_org_urls(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("mxhash", readme.lower())
        self.assertNotIn("gitea.", readme.lower())
        self.assertNotIn("harbor.", readme.lower())
        self.assertNotIn("Welcomeback", readme)
        self.assertIn("SECURITY.md", readme)
        self.assertIn("LICENSE", readme)

    def test_playbook_header_is_orchestrator_neutral(self) -> None:
        text = (REPO_ROOT / "playbooks" / "infra_hosts.yaml").read_text(encoding="utf-8")
        self.assertNotIn("clusterctl", text)
        self.assertNotIn("clusters/<id>", text)
        self.assertNotIn("vars-file.yml", text)
        self.assertNotIn("mxhash", text.lower())
        self.assertIn("tags: [00_ensure_workspace]", text)
        self.assertIn("tags: [01_validate_vars]", text)
        self.assertIn("infra_platform_hosts | default('infra_platform')", text)
        self.assertNotIn("hosts: infra_platform\n", text)
        self.assertIn("01_install_docker_engine", text)
        self.assertIn("03_deploy_bind_compose", text)

    def test_no_org_fingerprint_in_product_sources(self) -> None:
        needles = ("mxhash", "gitea.", "harbor.", "welcomeback", "upload.mxhash", "nexus.mxhash", "/var/lib/mxhash")
        hits = _scan_product_sources_for(needles)
        self.assertEqual(hits, [], f"org fingerprint in product sources: {hits}")

        for needle in ("vars-file.yml", "platform.yml", "clusters/<id>", "atlas-clusterctl", "./cluster "):
            overlay_hits = _scan_product_sources_for((needle,), case_sensitive=True)
            self.assertEqual(
                overlay_hits,
                [],
                f"orchestrator path in product sources ({needle}): {overlay_hits}",
            )

    def test_no_lab_password_fingerprint_in_product_sources(self) -> None:
        hits = _scan_product_sources_for(("Welcomeback",), case_sensitive=True)
        self.assertEqual(hits, [], f"lab password fingerprint in product sources: {hits}")

    def test_no_obvious_secret_material_in_product_sources(self) -> None:
        needles = ("Welcomeback", "BEGIN OPENSSH PRIVATE", "BEGIN RSA PRIVATE", "AKIA")
        hits = _scan_product_sources_for(needles, case_sensitive=True)
        self.assertEqual(hits, [], f"secret-like material found: {hits}")

    def test_no_cyrillic_in_product_sources(self) -> None:
        hits: list[str] = []
        for root in _PRODUCT_SCAN_ROOTS:
            if not root.exists():
                continue
            paths = [root] if root.is_file() else root.rglob("*")
            for path in paths:
                if not path.is_file():
                    continue
                if path.suffix.lower() not in _PRODUCT_SCAN_SUFFIXES and path.name != "run.sh":
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                if _CYRILLIC_RE.search(text):
                    hits.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(hits, [], f"Cyrillic residue in product sources: {hits[:20]}")

    def test_catalog_and_examples_are_inert(self) -> None:
        catalog = (REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.yml").read_text(encoding="utf-8")
        secrets_overlay = (REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.secrets.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("CHANGEME", secrets_overlay)
        self.assertIn("example.com", catalog)
        self.assertNotIn("mxhash", catalog.lower())
        self.assertNotIn("Welcomeback", catalog)
        self.assertNotIn("clusterctl", catalog.lower())
        self.assertNotIn("/var/lib/mxhash", catalog)
        secrets = (REPO_ROOT / "examples" / "secrets.example.yml").read_text(encoding="utf-8")
        self.assertIn("CHANGEME", secrets)
        self.assertNotIn("mxhash", secrets.lower())
        inventory = (REPO_ROOT / "inventory-example.yml").read_text(encoding="utf-8")
        self.assertIn("example.com", inventory)
        self.assertIn("192.0.2.", inventory)
        self.assertNotIn("mxhash", inventory.lower())

    def test_domain_check_script_exists_and_passes(self) -> None:
        path = REPO_ROOT / "scripts" / "check-no-hardcoded-domains.sh"
        self.assertTrue(path.is_file())
        self.assertTrue(path.stat().st_mode & 0o111, "check-no-hardcoded-domains.sh must be executable")
        text = path.read_text(encoding="utf-8")
        self.assertIn("mxhash", text)
        self.assertIn(r"upload\.mxhash", text)
        self.assertIn(r"nexus\.mxhash", text)
        self.assertIn("/var/lib/mxhash", text)
        self.assertIn("[Ww]elcomeback", text)
        result = subprocess.run(
            [str(path)],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_security_md_documents_history_fingerprint(self) -> None:
        text = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("containerd_config.toml", text)
        self.assertIn("nexus.mxhash.com", text)
        self.assertIn("/var/lib/mxhash", text)
        self.assertIn("e6501ad", text)
        self.assertIn("check-no-hardcoded-domains.sh", text)

    def test_dead_static_containerd_config_removed(self) -> None:
        dead = REPO_ROOT / "roles" / "02-configure-docker-daemon" / "files" / "containerd_config.toml"
        self.assertFalse(dead.exists())
        template = (
            REPO_ROOT / "roles" / "02-configure-docker-daemon" / "templates" / "containerd_config.toml.j2"
        )
        self.assertTrue(template.is_file())
        tmpl = template.read_text(encoding="utf-8")
        self.assertIn("nexus_host", tmpl)
        self.assertNotIn("mxhash", tmpl.lower())

    def test_roles_layout(self) -> None:
        for role in _EXPECTED_ROLES:
            tasks = REPO_ROOT / "roles" / role / "tasks"
            self.assertTrue(
                (tasks / "main.yaml").is_file() or any(tasks.glob("*.yaml")),
                role,
            )

    def test_bootstrap_default_state_dir_is_neutral(self) -> None:
        defaults = (REPO_ROOT / "roles" / "00-bootstrap-infra-repos" / "defaults" / "main.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("infra_bootstrap_repo_state_dir: /var/lib/atlas-infra", defaults)
        self.assertNotIn("/var/lib/mxhash", defaults)
        self.assertNotIn("clusterctl", defaults.lower())

    def test_workspace_role_is_standalone_safe(self) -> None:
        defaults = (REPO_ROOT / "roles" / "00_ensure_workspace" / "defaults" / "main.yml").read_text(
            encoding="utf-8"
        )
        validate = (REPO_ROOT / "roles" / "00_ensure_workspace" / "tasks" / "validate.yaml").read_text(
            encoding="utf-8"
        )
        create_dirs = (REPO_ROOT / "roles" / "00_ensure_workspace" / "tasks" / "create_dirs.yaml").read_text(
            encoding="utf-8"
        )
        catalog = (REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.yml").read_text(encoding="utf-8")
        for needle in (
            "cluster_workspace_id:",
            "cluster_workspace_parent:",
            "cluster_workspace_root:",
            "CLUSTER_WORKSPACE_ID",
            "CLUSTER_WORKSPACE_PARENT",
            "CLUSTER_WORKSPACE_ROOT",
        ):
            self.assertIn(needle, defaults, needle)
            self.assertIn(needle.replace(":", "") if needle.endswith(":") else needle, catalog)
        self.assertIn("Resolve cluster workspace id", validate)
        self.assertIn("Resolve cluster workspace parent", validate)
        self.assertIn("Resolve cluster workspace root", validate)
        self.assertIn("CLUSTER_WORKSPACE_PARENT", validate)
        self.assertIn("k8s_cluster_domain", validate)
        self.assertIn("cluster_domain", validate)
        self.assertIn(".ansible_facts_cache", create_dirs)
        self.assertIn("logs", create_dirs)
        # Must not mkdir absolute /kubeconfig when controller_* unset
        self.assertNotIn('}/kubeconfig"', create_dirs)
        self.assertNotIn("/kubeconfig", create_dirs)

    def test_validate_vars_covers_modes_and_secrets(self) -> None:
        main = (REPO_ROOT / "roles" / "01_validate_vars" / "tasks" / "main.yaml").read_text(encoding="utf-8")
        pull = (REPO_ROOT / "roles" / "01_validate_vars" / "tasks" / "pull_modes.yml").read_text(encoding="utf-8")
        secrets = (REPO_ROOT / "roles" / "01_validate_vars" / "tasks" / "secrets.yml").read_text(encoding="utf-8")
        cache = (REPO_ROOT / "roles" / "01_validate_vars" / "tasks" / "cache_sync.yml").read_text(encoding="utf-8")
        catalog = (REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.yml").read_text(encoding="utf-8")

        self.assertIn("include_tasks: pull_modes.yml", main)
        self.assertIn("include_tasks: helm_repo.yml", main)
        self.assertIn("include_tasks: secrets.yml", main)
        self.assertIn("include_tasks: cache_sync.yml", main)
        self.assertIn("include_tasks: cache_seed.yml", main)
        cache_seed = (REPO_ROOT / "roles" / "01_validate_vars" / "tasks" / "cache_seed.yml").read_text(
            encoding="utf-8"
        )
        helm_repo_validate = (
            REPO_ROOT / "roles" / "01_validate_vars" / "tasks" / "helm_repo.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("infra_cache_seed_load_enabled", cache_seed)
        self.assertIn("nginx_cache_sync_enabled", cache_seed)
        self.assertIn("cannot both", cache_seed)
        self.assertIn("helm_repo_releases_warm_specs", helm_repo_validate)
        self.assertIn("helm_repo_nginx_releases_github_allowlist", helm_repo_validate)
        self.assertIn("'..' not in (item.path | string)", helm_repo_validate)
        self.assertNotIn("for prefix in", helm_repo_validate)
        self.assertNotIn(".startswith(", helm_repo_validate)
        self.assertIn("regex_escape", helm_repo_validate)
        self.assertIn("dns_domain_suffix", main)
        self.assertIn("pki_ca_host:", catalog)
        self.assertIn('pki_ca_host: "ca.{{ dns_domain_suffix }}"', catalog)
        for needle in (
            "use_internal_rpm_apt_repo",
            "use_internal_helm_repo",
            "use_internal_docker_registry",
            "setup_apt_rpm_nginx",
            "setup_helm_nginx",
            "setup_registry",
            "get_snapshotter",
            "containerd_registry_mirrors",
            "pkg_repo_upstreams",
            "helm_repo_upstreams",
        ):
            self.assertIn(needle, pull, needle)
        self.assertIn("CHANGEME", secrets)
        self.assertIn("setup_bind", secrets)
        self.assertIn("bind_zones", secrets)
        self.assertIn("tsig_secret", secrets)
        self.assertIn("setup_stepca", secrets)
        self.assertIn("bind_zones:", catalog)
        self.assertIn("update_mode: allow-update", catalog)
        self.assertIn("inventory_a_records: true", catalog)
        self.assertNotIn("bind_apex_zone:", catalog)
        self.assertNotIn("bind_k8s_zone:", catalog)
        named = (REPO_ROOT / "roles" / "03-deploy-bind-compose" / "templates" / "named.conf.j2").read_text(
            encoding="utf-8"
        )
        self.assertIn("bind_zones.items()", named)
        self.assertNotIn("bind_apex_zone", named)
        self.assertNotIn("bind_k8s_zone", named)
        allow_update_branch = named.split(
            "{% if (zone.update_mode | default('zonesub')) == 'allow-update' %}",
            1,
        )[1].split("{% else %}", 1)[0]
        self.assertIn("allow-update { key {{ zone.tsig_key_name }}; };", allow_update_branch)
        self.assertIn("allow-transfer {", allow_update_branch)
        self.assertIn('key "{{ zone.tsig_key_name }}";', allow_update_branch)
        bind_render = (REPO_ROOT / "roles" / "03-deploy-bind-compose" / "tasks" / "render.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("bind_zones | dict2items", bind_render)
        self.assertIn("bind_sibling_zone_names", bind_render)
        self.assertIn("bind_zone_files_need_rewrite", bind_render)
        self.assertIn("rndc freeze", bind_render)
        self.assertIn("bind_union_zone_records", bind_render)
        self.assertIn("not (bind_container_running | bool)", bind_render)
        self.assertIn("nginx_cache_sync_remote_host", cache)
        self.assertIn("nginx_cache_sync_ownership_resolve", cache)
        self.assertIn("nginx_cache_sync_nginx_uid", cache)
        self.assertIn("nginx_cache_sync_nginx_gid", cache)
        self.assertIn("nginx_cache_sync_fresh_max_age_hours", cache)
        self.assertIn("nginx_cache_sync_stamp_path", cache)
        self.assertIn("nginx_cache_sync_parallel_jobs", cache)
        validate_defaults = (
            REPO_ROOT / "roles" / "01_validate_vars" / "defaults" / "main.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("nginx_cache_sync_nginx_uid: 101", validate_defaults)
        self.assertIn("nginx_cache_sync_nginx_gid: 101", validate_defaults)
        self.assertIn("nginx_cache_sync_ownership_resolve: static", validate_defaults)
        self.assertIn("helm_repo_releases_warm_specs: []", validate_defaults)
        self.assertIn("helm_repo_nginx_releases_github_allowlist: []", validate_defaults)
        self.assertIn("default(101, true)", cache)
        ownership = (
            REPO_ROOT / "roles" / "11-sync-infra-cache" / "tasks" / "fix_cache_ownership.yaml"
        ).read_text(encoding="utf-8")
        ownership_defaults = (
            REPO_ROOT / "roles" / "11-sync-infra-cache" / "defaults" / "main.yml"
        ).read_text(encoding="utf-8")
        sync_main = (
            REPO_ROOT / "roles" / "11-sync-infra-cache" / "tasks" / "main.yaml"
        ).read_text(encoding="utf-8")
        check_fresh = (
            REPO_ROOT / "roles" / "11-sync-infra-cache" / "tasks" / "check_fresh.yaml"
        ).read_text(encoding="utf-8")
        sync_pull = (
            REPO_ROOT / "roles" / "11-sync-infra-cache" / "tasks" / "sync_pull.yaml"
        ).read_text(encoding="utf-8")
        sync_push = (
            REPO_ROOT / "roles" / "11-sync-infra-cache" / "tasks" / "sync_push.yaml"
        ).read_text(encoding="utf-8")
        rsync_parallel = (
            REPO_ROOT / "roles" / "11-sync-infra-cache" / "tasks" / "rsync_parallel.yaml"
        ).read_text(encoding="utf-8")
        rsync_batch = (
            REPO_ROOT / "roles" / "11-sync-infra-cache" / "tasks" / "rsync_parallel_batch.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("nginx_cache_sync_ownership_resolve: static", ownership_defaults)
        self.assertIn("nginx_cache_sync_nginx_uid: 101", ownership_defaults)
        self.assertIn("nginx_cache_sync_nginx_gid: 101", ownership_defaults)
        self.assertIn("nginx_cache_sync_skip_if_fresh: false", ownership_defaults)
        self.assertIn("nginx_cache_sync_fresh_max_age_hours: 24", ownership_defaults)
        self.assertIn("cache-sync.stamp", ownership_defaults)
        self.assertIn("nginx_cache_sync_parallel: false", ownership_defaults)
        self.assertIn("nginx_cache_sync_parallel_jobs: 4", ownership_defaults)
        self.assertIn("nginx_cache_sync_remote_subdir_helm_releases: helm-releases", ownership_defaults)
        self.assertIn("Resolve nginx ownership ids from static defaults", ownership)
        # Default static path must not shell out to docker just for uid/gid.
        static_block = ownership.split("Resolve nginx uid via ownership image", 1)[0]
        self.assertNotRegex(static_block, r"(?m)^\s+cmd:.*docker run")
        self.assertNotIn("docker run --rm", static_block)
        self.assertIn("import_tasks: check_fresh.yaml", sync_main)
        self.assertIn("include_tasks: write_stamp.yaml", sync_main)
        self.assertIn("include_tasks: restart_services.yaml", sync_main)
        self.assertIn("nginx_cache_sync_skip_pull", sync_main)
        self.assertIn("service restart guarantee", sync_main)
        self.assertIn("always:", sync_main)
        self.assertLess(
            sync_main.index("import_tasks: check_fresh.yaml"),
            sync_main.index("service restart guarantee"),
        )
        self.assertIn("cache-sync-services.held", ownership_defaults)
        self.assertTrue(
            (REPO_ROOT / "roles" / "11-sync-infra-cache" / "tasks" / "load_services_hold.yaml").is_file()
        )
        self.assertTrue(
            (REPO_ROOT / "roles" / "11-sync-infra-cache" / "tasks" / "write_services_hold.yaml").is_file()
        )
        self.assertTrue(
            (REPO_ROOT / "roles" / "11-sync-infra-cache" / "tasks" / "restart_services.yaml").is_file()
        )
        self.assertIn("atlas_infra_cache_sync", check_fresh)
        self.assertIn("skipped_fresh", check_fresh)
        self.assertIn("fingerprint_match", check_fresh)
        self.assertTrue(
            (REPO_ROOT / "roles" / "11-sync-infra-cache" / "tasks" / "compute_remote_fingerprint.yaml").is_file()
        )
        self.assertIn("import_tasks: build_rsync_jobs.yaml", sync_pull)
        self.assertIn("import_tasks: rsync_serial.yaml", sync_pull)
        self.assertIn("import_tasks: rsync_parallel.yaml", sync_pull)
        self.assertIn("import_tasks: build_rsync_jobs.yaml", sync_push)
        self.assertIn("import_tasks: rsync_parallel.yaml", sync_push)
        self.assertIn("nginx_cache_sync_parallel", sync_pull)
        self.assertIn("batch(nginx_cache_sync_parallel_jobs", rsync_parallel)
        self.assertIn("async:", rsync_batch)
        self.assertIn("async_status:", rsync_batch)
        self.assertIn("Assert parallel rsync batch succeeded", rsync_batch)
        # Full public upstream / mirror SoT ships in all.yml; pull modes stay none
        # until enabled (same surface as orchestrated atlas-infra-edge.yml).
        self.assertIn("pkg_repo_upstreams:", catalog)
        self.assertIn("slug: debian-main", catalog)
        self.assertIn("helm_repo_upstreams:", catalog)
        self.assertIn("thanos-community", catalog)
        self.assertIn("thanos-community.github.io/helm-charts", catalog)
        self.assertIn("kyverno", catalog)
        self.assertIn("kyverno.github.io/kyverno", catalog)
        self.assertIn("policy-reporter", catalog)
        self.assertIn("kyverno.github.io/policy-reporter", catalog)
        self.assertNotIn("ingress-nginx", catalog)
        self.assertIn("containerd_registry_mirrors:", catalog)
        self.assertIn("dir_name: docker.io", catalog)
        self.assertIn("dir_name: reg.kyverno.io", catalog)
        self.assertRegex(
            catalog, r'dir_name: reg\.kyverno\.io\n\s+server: "https://ghcr.io"'
        )
        self.assertIn("dir_name: cr.fluentbit.io", catalog)
        self.assertRegex(
            catalog,
            r'dir_name: cr\.fluentbit\.io\n\s+server: "https://registry-1.docker.io"',
        )
        self.assertNotIn("pkg_repo_upstreams: []", catalog)
        self.assertNotIn("helm_repo_upstreams: []", catalog)
        self.assertNotIn("containerd_registry_mirrors: []", catalog)
        self.assertIn("harbor_host:", catalog)
        self.assertIn("registry_tls_enabled: true", catalog)
        self.assertIn("pkg_repo_tls_enabled: true", catalog)

    def test_playbook_remote_tags_are_task_scoped(self) -> None:
        playbook = (REPO_ROOT / "playbooks" / "infra_hosts.yaml").read_text(encoding="utf-8")
        self.assertIn("tags: [00_ensure_workspace]", playbook)
        self.assertIn("tags: [01_validate_vars]", playbook)
        self.assertIn("01_install_docker_engine", playbook)
        self.assertIn("06_enable_compose_systemd_reconcile", playbook)
        self.assertIn("compose_render", playbook)
        self.assertIn("compose_start_core", playbook)
        self.assertIn("compose_start_registry", playbook)
        self.assertIn("before registry start", playbook)
        # Remote plays must not carry role-tag unions (Ansible inherits play tags onto every task).
        self.assertIn("Do not put role tag unions on the play", playbook)
        self.assertIn("Gather facts for docker roles", playbook)
        self.assertIn("Gather facts for compose roles", playbook)
        remote_plays = re.findall(
            r"- hosts: \"\{\{ infra_platform_hosts \| default\('infra_platform'\) \}\}\""
            r".*?(?=\n- hosts:|\Z)",
            playbook,
            flags=re.S,
        )
        self.assertEqual(len(remote_plays), 2, "expected docker + compose remote plays")
        for play in remote_plays:
            head = play.split("\n  pre_tasks:", 1)[0]
            self.assertNotRegex(
                head,
                r"(?m)^\s+tags:\s*$",
                "remote play must not declare play-level tags before pre_tasks",
            )
            self.assertIn("gather_facts: false", head)

        # helm_repo_cache_warm is owned by the warm-only include, not Deploy.
        self.assertIn("Do not attach helm_repo_cache_warm here", playbook)
        deploy_helm = re.search(
            r"name: Deploy Helm chart nginx HTTPS cache \(legacy tag\)\n(?:.*\n){0,20}?\s+tags: \[([^\]]+)\]",
            playbook,
        )
        self.assertIsNotNone(deploy_helm)
        self.assertNotIn("helm_repo_cache_warm", deploy_helm.group(1))
        self.assertRegex(
            playbook,
            r"name: Warm Helm chart nginx proxy cache \(explicit tag only\)\n(?:.*\n){0,12}?\s+tags: \[helm_repo_cache_warm\]",
        )

    def test_inventory_group_targeting(self) -> None:
        playbook = (REPO_ROOT / "playbooks" / "infra_hosts.yaml").read_text(encoding="utf-8")
        validate = (REPO_ROOT / "roles" / "01_validate_vars" / "tasks" / "main.yaml").read_text(
            encoding="utf-8"
        )
        defaults = (REPO_ROOT / "roles" / "01_validate_vars" / "defaults" / "main.yml").read_text(
            encoding="utf-8"
        )
        catalog = (REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.yml").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("infra_platform_hosts | default('infra_platform')", playbook)
        self.assertIn("groups[infra_platform_hosts]", validate)
        self.assertIn("infra_platform_hosts={{ infra_platform_hosts }}", validate)
        self.assertNotIn("groups['infra_platform']", validate)
        self.assertIn("infra_platform_hosts: infra_platform", defaults)
        self.assertIn("infra_platform_hosts: infra_platform", catalog)
        self.assertIn("infra_platform_hosts", readme)
        self.assertIn("my_infra_nodes", readme)
        self.assertLess(
            playbook.index("00_ensure_workspace"),
            playbook.index("01_validate_vars"),
        )
        self.assertLess(
            playbook.index("01_validate_vars"),
            playbook.index("infra_platform_hosts | default('infra_platform')"),
        )

    def test_ci_entrypoint_artifacts(self) -> None:
        self.assertTrue((REPO_ROOT / ".ansible-lint").is_file())
        self.assertTrue((REPO_ROOT / ".github" / "workflows" / "ci.yml").is_file())
        self.assertTrue((REPO_ROOT / "requirements-dev.txt").is_file())
        run_ci = REPO_ROOT / "tests" / "run_ci.sh"
        self.assertTrue(run_ci.is_file())
        self.assertTrue(run_ci.stat().st_mode & 0o111, "tests/run_ci.sh must be executable")
        run_ci_text = run_ci.read_text(encoding="utf-8")
        for needle in (
            "unittest",
            "syntax-check",
            "ansible-lint",
            "check-no-hardcoded-domains.sh",
            "playbooks/infra_hosts.yaml",
        ):
            self.assertIn(needle, run_ci_text, needle)
        workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("ansible-lint --profile min", workflow)
        self.assertIn("check-no-hardcoded-domains.sh", workflow)
        self.assertIn("playbooks/infra_hosts.yaml", workflow)
        self.assertNotIn("run_lab_idempotency.sh", workflow)
        lint_cfg = (REPO_ROOT / ".ansible-lint").read_text(encoding="utf-8")
        self.assertIn("profile: min", lint_cfg)
        reqs = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertIn("ansible-lint", reqs)

    def test_pkg_repo_warm_and_nginx_ipv4_hardening(self) -> None:
        warm = (
            REPO_ROOT
            / "roles"
            / "08-deploy-pkg-repo-nginx-compose"
            / "templates"
            / "warm-pkg-repo-cache.sh.j2"
        ).read_text(encoding="utf-8")
        warm_tasks = (
            REPO_ROOT / "roles" / "08-deploy-pkg-repo-nginx-compose" / "tasks" / "warm_cache.yaml"
        ).read_text(encoding="utf-8")
        role08_main = (
            REPO_ROOT / "roles" / "08-deploy-pkg-repo-nginx-compose" / "tasks" / "main.yaml"
        ).read_text(encoding="utf-8")
        role08_render = (
            REPO_ROOT / "roles" / "08-deploy-pkg-repo-nginx-compose" / "tasks" / "render.yaml"
        ).read_text(encoding="utf-8")
        role08_runtime = (
            REPO_ROOT / "roles" / "08-deploy-pkg-repo-nginx-compose" / "tasks" / "apply_runtime.yaml"
        ).read_text(encoding="utf-8")
        defaults = (
            REPO_ROOT / "roles" / "08-deploy-pkg-repo-nginx-compose" / "defaults" / "main.yml"
        ).read_text(encoding="utf-8")
        vhosts = (
            REPO_ROOT
            / "roles"
            / "08-deploy-pkg-repo-nginx-compose"
            / "templates"
            / "pkg-repo-vhosts.conf.j2"
        ).read_text(encoding="utf-8")
        reg_compose = (
            REPO_ROOT
            / "roles"
            / "07-deploy-registry-nginx-compose"
            / "templates"
            / "docker-compose.yml.j2"
        ).read_text(encoding="utf-8")
        reg_nginx = (
            REPO_ROOT / "roles" / "07-deploy-registry-nginx-compose" / "templates" / "nginx.conf.j2"
        ).read_text(encoding="utf-8")
        reg_runtime = (
            REPO_ROOT / "roles" / "07-deploy-registry-nginx-compose" / "tasks" / "apply_runtime.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn("disable_ipv6: 1", reg_compose)
        self.assertIn("ipv4=on", reg_nginx)
        self.assertIn("ipv6=off", reg_nginx)
        self.assertIn("set $pkg_repo_upstream", vhosts)
        self.assertIn("proxy_pass $pkg_repo_upstream$uri", vhosts)
        # Explicitly disable 301/302 cache — nginx still caches redirects by default
        # via Cache-Control/Expires (packages.gitlab.com → GCS signed URLs expire).
        self.assertIn("proxy_cache_valid 301 302 0", vhosts)
        self.assertIn("proxy_ignore_headers Cache-Control Expires Set-Cookie", vhosts)
        self.assertNotIn("proxy_cache_valid 200 206 302", vhosts)
        self.assertIn("proxy_cache_valid 200 206 {{ pkg_repo_nginx_cache_valid_success }}", vhosts)
        self.assertIn("proxy_cache_valid 200 206 {{ pkg_repo_nginx_cache_valid_metadata }}", vhosts)
        self.assertIn('WARM_MODE="{{ pkg_repo_nginx_cache_warm_mode | default(\'light\') }}"', warm)
        self.assertIn("curl -4", warm)
        self.assertIn("primary.xml.gz", warm)
        self.assertIn("skip huge sqlite", warm)
        self.assertNotIn("filelists.sqlite", warm)
        self.assertIn("failed_when: false", warm_tasks)
        self.assertIn("pkg_repo_nginx_cache_warm_mode: light", defaults)
        self.assertIn("import_tasks: render.yaml", role08_main)
        self.assertNotIn("import_tasks: apply_runtime.yaml", role08_main)
        self.assertNotIn("pre_pull_compose_images.yaml", role08_main)
        self.assertIn("Mark pkg-repo metadata cache warm pending after vhost change", role08_render)
        self.assertIn("pkg_repo_cache_warm_pending", role08_render)
        self.assertIn("Reload registry nginx after nginx.conf change", reg_runtime)
        self.assertIn("Recreate registry nginx container after compose definition change", reg_runtime)
        self.assertNotIn("pre_pull_compose_images.yaml", role08_runtime)
        self.assertNotIn("pre_pull_compose_images.yaml", reg_runtime)

        cfg = (REPO_ROOT / "ansible.cfg").read_text(encoding="utf-8")
        self.assertIn("roles_path = roles", cfg)
        self.assertIn("filter_plugins = ./filter_plugins", cfg)
        self.assertIn("fact_caching = jsonfile", cfg)
        self.assertIn("fact_caching_connection = ./workspace/.ansible_facts_cache", cfg)
        run_sh = (REPO_ROOT / "run.sh").read_text(encoding="utf-8")
        self.assertIn("ANSIBLE_CACHE_PLUGIN_CONNECTION", run_sh)
        self.assertIn(".ansible_facts_cache", run_sh)
        helm_main = (
            REPO_ROOT / "roles" / "09-deploy-helm-repo-nginx-compose" / "tasks" / "main.yaml"
        ).read_text(encoding="utf-8")
        helm_runtime = (
            REPO_ROOT / "roles" / "09-deploy-helm-repo-nginx-compose" / "tasks" / "apply_runtime.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("import_tasks: render.yaml", helm_main)
        self.assertNotIn("import_tasks: apply_runtime.yaml", helm_main)
        self.assertNotIn("pre_pull_compose_images.yaml", helm_main)
        self.assertNotIn("pre_pull_compose_images.yaml", helm_runtime)
        self.assertNotIn("Warm helm-repo nginx chart cache after vhost deploy changes", helm_runtime)
        self.assertNotIn("'helm_repo_cache_warm' in ansible_run_tags", helm_runtime)
        helm_vhosts = (
            REPO_ROOT
            / "roles"
            / "09-deploy-helm-repo-nginx-compose"
            / "templates"
            / "helm-repo-vhosts.conf.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("location = /index.yaml", helm_vhosts)
        self.assertIn("proxy_read_timeout 30s;", helm_vhosts)
        self.assertGreaterEqual(helm_vhosts.count("proxy_read_timeout 900s;"), 2)

    def test_helm_repo_index_two_layer_cache(self) -> None:
        """Raw origin index is cached on loopback; public /index.yaml only rewrites."""
        catalog = (REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.yml").read_text(
            encoding="utf-8"
        )
        defaults = (
            REPO_ROOT
            / "roles"
            / "09-deploy-helm-repo-nginx-compose"
            / "defaults"
            / "main.yml"
        ).read_text(encoding="utf-8")
        helm_vhosts = (
            REPO_ROOT
            / "roles"
            / "09-deploy-helm-repo-nginx-compose"
            / "templates"
            / "helm-repo-vhosts.conf.j2"
        ).read_text(encoding="utf-8")
        registry_nginx = (
            REPO_ROOT
            / "roles"
            / "07-deploy-registry-nginx-compose"
            / "templates"
            / "nginx.conf.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("helm_repo_nginx_cache_valid_index: 24h", catalog)
        self.assertIn("helm_repo_nginx_index_origin_port: 18080", catalog)
        self.assertIn("helm_repo_nginx_cache_valid_index: 24h", defaults)
        self.assertIn("helm_repo_nginx_index_origin_port: 18080", defaults)
        self.assertIn("$upstream_cache_status", registry_nginx)
        self.assertIn(
            "listen 127.0.0.1:{{ helm_repo_nginx_index_origin_port }}", helm_vhosts
        )
        self.assertIn("allow 127.0.0.1;", helm_vhosts)
        self.assertIn("deny all;", helm_vhosts)
        self.assertIn(
            "location = /raw/{{ proxy.proxy_hostname }}/index.yaml", helm_vhosts
        )
        self.assertIn(
            'proxy_cache_key "helm-index:{{ proxy.proxy_hostname }}";', helm_vhosts
        )
        self.assertIn(
            "proxy_cache_valid 200 {{ helm_repo_nginx_cache_valid_index }};",
            helm_vhosts,
        )
        self.assertIn(
            "proxy_pass http://127.0.0.1:{{ helm_repo_nginx_index_origin_port }}/raw/{{ proxy.proxy_hostname }}/index.yaml;",
            helm_vhosts,
        )
        public = helm_vhosts.split("location = /index.yaml {", 1)[1].split(
            "location / {", 1
        )[0]
        self.assertIn("proxy_no_cache 1;", public)
        self.assertIn("proxy_cache_bypass 1;", public)
        self.assertIn("sub_filter", public)
        self.assertIn("proxy_read_timeout 35s;", public)
        self.assertNotIn("proxy_cache helm_repo_cache;", public)
        self.assertNotIn("proxy_ignore_headers Cache-Control Expires Set-Cookie;", public)
        self.assertNotIn("proxy_ssl_name {{ proxy.upstream_host }}", public)
        chart_proxy = (
            helm_vhosts.split("location = /index.yaml {", 1)[1]
            .split("location / {", 1)[1]
            .split("\n    }\n", 1)[0]
        )
        self.assertIn("proxy_cache helm_repo_cache;", chart_proxy)
        self.assertIn("proxy_ignore_headers Cache-Control Expires Set-Cookie;", chart_proxy)
        self.assertIn("proxy_hide_header Set-Cookie;", chart_proxy)
        self.assertIn("proxy_hide_header Set-Cookie;", helm_vhosts.split("location ^~ /@chart/{{ chart_host }}/ {", 1)[1].split("{% endif %}", 1)[0])
        inner = helm_vhosts.split(
            "location = /raw/{{ proxy.proxy_hostname }}/index.yaml {", 1
        )[1]
        inner = inner.split("\n{% endfor %}", 1)[0]
        self.assertIn("proxy_cache helm_repo_cache;", inner)
        self.assertIn("proxy_ignore_headers Cache-Control Expires Set-Cookie;", inner)
        self.assertIn("proxy_connect_timeout 10s;", inner)
        self.assertIn("proxy_read_timeout 30s;", inner)
        self.assertIn("proxy_ssl_name {{ proxy.upstream_host }};", inner)
        self.assertNotIn("sub_filter", inner)
        self.assertNotIn("proxy_no_cache 1;", inner)

    def test_helm_repo_cache_warm_installs_pyyaml_by_os(self) -> None:
        """warm-helm-repo-cache.py needs PyYAML: python3-yaml on Debian, python3-pyyaml on RHEL."""
        defaults = (
            REPO_ROOT
            / "roles"
            / "09-deploy-helm-repo-nginx-compose"
            / "defaults"
            / "main.yml"
        ).read_text(encoding="utf-8")
        warm = (
            REPO_ROOT
            / "roles"
            / "09-deploy-helm-repo-nginx-compose"
            / "tasks"
            / "warm_cache.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "helm_repo_nginx_cache_warm_pyyaml_package_debian: python3-yaml",
            defaults,
        )
        self.assertIn(
            "helm_repo_nginx_cache_warm_pyyaml_package_redhat: python3-pyyaml",
            defaults,
        )
        self.assertIn("Install PyYAML for helm-repo cache warm (Debian/Ubuntu)", warm)
        self.assertIn("Install PyYAML for helm-repo cache warm (Red Hat family)", warm)
        self.assertIn("helm_repo_nginx_cache_warm_pyyaml_package_debian", warm)
        self.assertIn("helm_repo_nginx_cache_warm_pyyaml_package_redhat", warm)
        self.assertIn("ansible_facts['os_family'] == 'Debian'", warm)
        self.assertIn("ansible_facts['os_family'] == 'RedHat'", warm)
        self.assertIn("Assert PyYAML is importable for helm-repo cache warm", warm)

    def test_helm_repo_cache_warm_urllib_timeout_is_scalar(self) -> None:
        """Python 3.13 urllib.urlopen rejects timeout=(connect, read) tuples."""
        script = (
            REPO_ROOT
            / "roles"
            / "09-deploy-helm-repo-nginx-compose"
            / "templates"
            / "warm-helm-repo-cache.py.j2"
        ).read_text(encoding="utf-8")
        self.assertNotIn("timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)", script)
        self.assertIn("timeout=TIMEOUT", script)
        self.assertIn("urllib.parse.urljoin", script)
        self.assertIn("RELEASES_DIR", script)
        self.assertIn("GITHUB_CHART_MARK", script)
        self.assertIn("https://github.com/", script)
        self.assertNotIn("/var/cache/nginx/helm-repo", script)
        self.assertIn("0o755", script)
        self.assertIn("while True:", script)
        self.assertIn("chown_store_path", script)

        releases_warm = (
            REPO_ROOT
            / "roles"
            / "09-deploy-helm-repo-nginx-compose"
            / "templates"
            / "warm-helm-releases.py.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("RELEASES_DIR", releases_warm)
        self.assertIn("https://github.com/", releases_warm)
        self.assertIn("try_files miss", releases_warm)
        self.assertNotIn("se=", releases_warm)
        self.assertNotIn("/var/cache/nginx/helm-repo", releases_warm)
        self.assertIn("0o755", releases_warm)
        self.assertIn("while True:", releases_warm)
        self.assertIn("chown_store_path", releases_warm)

        warm_tasks = (
            REPO_ROOT
            / "roles"
            / "09-deploy-helm-repo-nginx-compose"
            / "tasks"
            / "warm_cache.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("helm_repo_releases_warm_specs", warm_tasks)
        self.assertIn("warm-helm-releases.py", warm_tasks)

    def test_helm_repo_raw_github_vhost(self) -> None:
        """Dedicated raw.helm.* vhost: allowlist, 24h cache, stale 429, not chart_hosts."""
        catalog = (REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'helm_repo_nginx_raw_host: "raw.{{ helm_repo_nginx_ingress_domain }}"',
            catalog,
        )
        self.assertIn("helm_repo_nginx_cache_valid_raw: 24h", catalog)
        self.assertIn("helm_repo_nginx_raw_github_allowlist:", catalog)
        for prefix in (
            "istio/istio",
            "ceph/ceph",
            "envoyproxy/gateway",
            "thanos-io/thanos",
            "falcosecurity/charts",
            "cloudnative-pg/grafana-dashboards",
            "keycloak/keycloak-grafana-dashboard",
            "argoproj/argo-cd",
            "argoproj/argo-rollouts",
            "external-secrets/external-secrets",
            "jaegertracing/jaeger",
            "projectcalico/calico",
        ):
            self.assertIn(f"- {prefix}", catalog)
        self.assertIn('name: "*.helm"', catalog)
        self.assertNotIn("raw.githubusercontent.com", catalog)
        helm_vhosts = (
            REPO_ROOT
            / "roles"
            / "09-deploy-helm-repo-nginx-compose"
            / "templates"
            / "helm-repo-vhosts.conf.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("server_name {{ helm_repo_nginx_raw_host }}", helm_vhosts)
        self.assertIn("proxy_pass https://raw.githubusercontent.com;", helm_vhosts)
        self.assertIn("proxy_set_header Host raw.githubusercontent.com;", helm_vhosts)
        self.assertIn(
            "location ^~ /{{ prefix }}/",
            helm_vhosts,
        )
        self.assertIn("helm_repo_nginx_raw_github_allowlist", helm_vhosts)
        self.assertIn("proxy_cache helm_repo_cache;", helm_vhosts)
        self.assertIn("proxy_cache_lock on;", helm_vhosts)
        self.assertIn(
            "proxy_cache_valid 200 206 {{ helm_repo_nginx_cache_valid_raw }};",
            helm_vhosts,
        )
        self.assertIn(
            "proxy_cache_use_stale error timeout updating http_403 http_429 http_500 http_502 http_503 http_504;",
            helm_vhosts,
        )
        self.assertIn("return 403;", helm_vhosts)
        self.assertNotIn(
            "location ^~ /@chart/raw.githubusercontent.com/",
            helm_vhosts,
        )
        self.assertIn("helm_repo_nginx_cache_valid_gnet: 30d", catalog)
        self.assertIn("helm_repo_nginx_gnet_allowlist:", catalog)
        for gnet_id in (
            "3244",
            "12175",
            "20162",
            "12904",
            "18855",
            "20340",
            "14191",
            "7587",
            "13396",
            "15038",
            "15918",
            "15983",
            "17813",
            "16337",
            "22208",
        ):
            self.assertIn(f"- {gnet_id}", catalog)
        self.assertNotIn("- 21065", catalog)
        self.assertNotIn("charts.kasten.io", catalog)
        self.assertNotIn("name: kasten", catalog)
        self.assertIn("/api/dashboards/", helm_vhosts)
        self.assertIn("helm_repo_nginx_gnet_allowlist", helm_vhosts)
        self.assertIn("proxy_pass https://grafana.com;", helm_vhosts)
        self.assertIn("proxy_set_header Host grafana.com;", helm_vhosts)
        self.assertIn("proxy_ssl_name grafana.com;", helm_vhosts)
        self.assertIn(
            "proxy_cache_valid 200 206 {{ helm_repo_nginx_cache_valid_gnet }};",
            helm_vhosts,
        )
        self.assertNotIn("location ^~ /@chart/grafana.com/", helm_vhosts)
        issue = (
            REPO_ROOT
            / "roles"
            / "09-deploy-helm-repo-nginx-compose"
            / "templates"
            / "issue-helm-repo-tls-cert.sh.j2"
        ).read_text(encoding="utf-8")
        self.assertIn('--san "*.{{ helm_repo_nginx_ingress_domain }}"', issue)

    def test_helm_repo_releases_github_vhost(self) -> None:
        """Dedicated releases.helm.* vhost: file store try_files, no SAS proxy_cache."""
        catalog = (REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'helm_repo_nginx_releases_host: "releases.{{ helm_repo_nginx_ingress_domain }}"',
            catalog,
        )
        self.assertNotIn("helm_repo_nginx_cache_valid_releases", catalog)
        self.assertIn("helm_repo_nginx_releases_dir: /opt/helm-repo-nginx/releases", catalog)
        self.assertIn("helm_repo_releases_warm_specs: []", catalog)
        self.assertIn("helm_repo_nginx_releases_github_allowlist:", catalog)
        for prefix in (
            "projectcalico/calico/releases/download",
            "istio/istio/releases/download",
            "etcd-io/etcd/releases/download",
            "vmware/pinniped/releases/download",
        ):
            self.assertIn(f"- {prefix}", catalog)
        self.assertIn("custom_nginx_content:", catalog)
        self.assertIn("external-snapshotter", catalog)
        helm_vhosts = (
            REPO_ROOT
            / "roles"
            / "09-deploy-helm-repo-nginx-compose"
            / "templates"
            / "helm-repo-vhosts.conf.j2"
        ).read_text(encoding="utf-8")
        self.assertIn("server_name {{ helm_repo_nginx_releases_host }}", helm_vhosts)
        self.assertIn("proxy_pass https://github.com;", helm_vhosts)
        self.assertIn("proxy_set_header Host github.com;", helm_vhosts)
        self.assertIn("helm_repo_nginx_releases_github_allowlist", helm_vhosts)
        self.assertIn(
            "proxy_redirect https://release-assets.githubusercontent.com/ https://$host/@chart/release-assets.githubusercontent.com/;",
            helm_vhosts,
        )
        self.assertIn(
            "location ^~ /@chart/release-assets.githubusercontent.com/",
            helm_vhosts,
        )
        self.assertIn("location ^~ /@chart/github.com/", helm_vhosts)
        self.assertIn("root /var/cache/nginx/helm-releases;", helm_vhosts)
        self.assertIn("try_files $uri @github_releases;", helm_vhosts)
        self.assertIn("try_files $uri @chart_github_releases;", helm_vhosts)
        self.assertIn("location @github_releases {", helm_vhosts)
        self.assertIn("location @chart_github_releases {", helm_vhosts)
        self.assertIn("add_header X-Cache-Status STORE always;", helm_vhosts)
        self.assertIn("proxy_cache off;", helm_vhosts)
        self.assertNotIn("proxy_store", helm_vhosts)
        self.assertNotIn(
            "proxy_cache_valid 200 206 {{ helm_repo_nginx_cache_valid_releases }};",
            helm_vhosts,
        )
        self.assertIn("proxy_pass https://release-assets.githubusercontent.com;", helm_vhosts)
        raw_idx = helm_vhosts.index("server_name {{ helm_repo_nginx_raw_host }}")
        rel_idx = helm_vhosts.index("server_name {{ helm_repo_nginx_releases_host }}")
        self.assertLess(raw_idx, rel_idx)
        self.assertNotIn(
            "location ^~ /@chart/github.com/",
            helm_vhosts[rel_idx:],
        )
        compose09 = (
            REPO_ROOT
            / "roles"
            / "09-deploy-helm-repo-nginx-compose"
            / "templates"
            / "docker-compose.yml.j2"
        ).read_text(encoding="utf-8")
        compose07 = (
            REPO_ROOT
            / "roles"
            / "07-deploy-registry-nginx-compose"
            / "templates"
            / "docker-compose.yml.j2"
        ).read_text(encoding="utf-8")
        render09 = (
            REPO_ROOT
            / "roles"
            / "09-deploy-helm-repo-nginx-compose"
            / "tasks"
            / "render.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("helm_repo_nginx_releases_dir", compose09)
        self.assertIn("/var/cache/nginx/helm-releases:ro", compose09)
        self.assertIn("/var/cache/nginx/helm-releases:ro", compose07)
        self.assertIn("{{ helm_repo_nginx_releases_dir }}", render09)
        self.assertIn(
            'find "{{ helm_repo_nginx_cache_dir }}" -mindepth 1 -delete',
            render09,
        )
        self.assertNotIn("helm_repo_nginx_releases_dir }}\" -mindepth 1 -delete", render09)
        pre_sync = (
            REPO_ROOT / "roles" / "11-sync-infra-cache" / "tasks" / "pre_sync.yaml"
        ).read_text(encoding="utf-8")
        ownership = (
            REPO_ROOT / "roles" / "11-sync-infra-cache" / "tasks" / "fix_cache_ownership.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("helm-releases", pre_sync)
        self.assertIn("helm_repo_nginx_releases_dir", pre_sync)
        self.assertIn("helm_repo_nginx_releases_dir", ownership)
        for role_defaults in (
            REPO_ROOT / "roles" / "07-deploy-registry-nginx-compose" / "defaults" / "main.yml",
            REPO_ROOT / "roles" / "11-sync-infra-cache" / "defaults" / "main.yml",
            REPO_ROOT / "roles" / "14-infra-cache-seed" / "defaults" / "main.yml",
        ):
            self.assertIn(
                "helm_repo_nginx_releases_dir: /opt/helm-repo-nginx/releases",
                role_defaults.read_text(encoding="utf-8"),
                role_defaults,
            )
        readme09 = (
            REPO_ROOT / "roles" / "09-deploy-helm-repo-nginx-compose" / "README.md"
        ).read_text(encoding="utf-8")
        self.assertIn("try_files", readme09)
        self.assertIn("helm_repo_releases_warm_specs", readme09)

    def test_infra_stats_shared_registry_contract(self) -> None:
        catalog = (REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("setup_infra_stats: false", catalog)
        self.assertIn("infra_stats_hostname:", catalog)
        self.assertIn("infra_stats_path: /stats", catalog)
        self.assertIn("infra_stats_scrape_dir:", catalog)
        self.assertIn("bind_apex_static_records_stats:", catalog)

        role = REPO_ROOT / "roles" / "13-deploy-infra-stats"
        self.assertTrue((role / "tasks" / "render.yaml").is_file())
        self.assertTrue((role / "tasks" / "scrape.yaml").is_file())
        self.assertTrue((role / "tasks" / "publish.yaml").is_file())
        self.assertTrue((role / "tasks" / "pre_start.yaml").is_file())
        self.assertTrue((role / "templates" / "stats.html.j2").is_file())
        self.assertTrue((role / "templates" / "stats.json.j2").is_file())
        self.assertTrue((role / "templates" / "refresh_infra_stats.py.j2").is_file())
        self.assertTrue((role / "templates" / "refresh-infra-stats.sh.j2").is_file())
        self.assertTrue((role / "templates" / "publish_context.json.j2").is_file())
        context = (role / "templates" / "publish_context.json.j2").read_text(
            encoding="utf-8"
        )
        self.assertIn("helm_repo_nginx_releases_dir", context)
        self.assertIn("pkg_repo_nginx_cache_dir", context)
        self.assertIn("cache_html_limit", context)
        self.assertIn("cache_json_limit", context)
        self.assertIn("setup_custom_content_nginx", context)
        self.assertIn("ca_root_path", context)
        self.assertIn("ca_step_url", context)
        self.assertIn("ca_upstream_urls", context)
        self.assertTrue((role / "templates" / "infra-stats-refresh.cron.j2").is_file())
        self.assertTrue((role / "templates" / "infra-stats-vhosts.conf.j2").is_file())
        self.assertTrue((role / "templates" / "issue-infra-stats-tls-cert.sh.j2").is_file())

        self.assertIn("infra_stats_refresh_cron_enabled:", catalog)
        self.assertIn('infra_stats_refresh_cron_minute: "*/10"', catalog)
        self.assertIn("infra_stats_refresh_cron_log_file:", catalog)

        defaults = (role / "defaults" / "main.yml").read_text(encoding="utf-8")
        self.assertIn("infra_stats_refresh_cron_enabled: true", defaults)
        self.assertIn('infra_stats_refresh_cron_minute: "*/10"', defaults)
        self.assertIn("infra_stats_refresh_cron_hour:", defaults)
        self.assertIn("infra_stats_refresh_cron_dom:", defaults)
        self.assertIn("infra_stats_refresh_cron_month:", defaults)
        self.assertIn("infra_stats_refresh_cron_dow:", defaults)
        self.assertIn("infra_stats_refresh_cron_log_file:", defaults)
        self.assertIn("infra_stats_cache_html_limit: 200", defaults)
        self.assertIn("infra_stats_cache_json_limit: 2000", defaults)

        vhost = (role / "templates" / "infra-stats-vhosts.conf.j2").read_text(encoding="utf-8")
        self.assertIn("return 302 {{ infra_stats_path }}", vhost)
        self.assertIn("server_name {{ infra_stats_hostname }}", vhost)
        self.assertIn("alias {{ infra_stats_html_container_path }}/stats.html", vhost)
        self.assertNotIn("location {{ infra_stats_path }}/", vhost)
        self.assertNotIn("root {{ infra_stats_html_container_path }}", vhost)
        self.assertNotRegex(vhost, r"(?m)^\s*root\s+")
        self.assertIn("location = /ca/roots.pem", vhost)
        self.assertIn("location = /ca/install-root-ca-debian.sh", vhost)
        self.assertIn("location = /ca/install-root-ca-rhel.sh", vhost)
        self.assertIn("application/x-pem-file", vhost)
        self.assertIn("text/x-shellscript", vhost)

        scrape_py = (role / "templates" / "refresh_infra_stats.py.j2").read_text(
            encoding="utf-8"
        )
        self.assertIn("chronyc", scrape_py)
        self.assertIn("reference_name", scrape_py)
        self.assertIn("len(cols) >= 14", scrape_py)
        self.assertIn("bind_zones.json", scrape_py)
        self.assertIn("ntp.json", scrape_py)
        self.assertIn("certs.json", scrape_py)
        self.assertIn("issued_certs.json", scrape_py)
        self.assertIn("cache.json", scrape_py)
        self.assertIn("scrape_cache", scrape_py)
        self.assertIn("ratelimitpreview/test", scrape_py)
        self.assertIn("scrape_docker_hub", scrape_py)
        self.assertIn("publish_ca_files", scrape_py)
        self.assertIn("install-root-ca-debian.sh", scrape_py)
        self.assertIn("set -euo pipefail", scrape_py)
        self.assertNotIn("${{", scrape_py)
        self.assertIn('URL="${CA_PEM_URL:-', scrape_py)
        self.assertIn("nginx_cache_key", scrape_py)
        self.assertIn('b"\\nKEY: "', scrape_py)
        self.assertIn("_manifests/tags", scrape_py)
        self.assertIn("helm-releases", scrape_py)
        self.assertIn("pkg-metadata", scrape_py)
        self.assertIn('db.glob("*.vlog")', scrape_py)
        self.assertNotIn('db / "000000.vlog"', scrape_py)
        self.assertIn("tag == 0x81", scrape_py)
        self.assertIn("tag == 0x82", scrape_py)
        self.assertIn("os.replace(", scrape_py)
        self.assertIn('.tmp"', scrape_py)
        self.assertIn("os.unlink(tmp)", scrape_py)
        self.assertIn('row["on_disk"]', scrape_py)
        self.assertIn("soft_scrape", scrape_py)
        self.assertIn("annotate_on_disk", scrape_py)
        self.assertIn("cron-refresh", scrape_py)
        self.assertIn("INFRA_STATS_GENERATED_BY", scrape_py)

        scrape = (role / "tasks" / "scrape.yaml").read_text(encoding="utf-8")
        self.assertIn("refresh_infra_stats.py", scrape)

        refresh_sh = (role / "templates" / "refresh-infra-stats.sh.j2").read_text(
            encoding="utf-8"
        )
        self.assertIn("flock -w", refresh_sh)
        self.assertNotIn("flock -n", refresh_sh)
        self.assertIn("rc=$?", refresh_sh)
        self.assertIn('"$rc" -ne 0', refresh_sh)
        self.assertIn("infra-stats refresh failed", refresh_sh)
        self.assertNotIn("if ! flock", refresh_sh)
        self.assertIn("refresh_infra_stats.py", refresh_sh)

        refresh_cron = (role / "templates" / "infra-stats-refresh.cron.j2").read_text(
            encoding="utf-8"
        )
        self.assertIn("infra_stats_refresh_cron_minute", refresh_cron)
        self.assertIn("refresh-infra-stats.sh", refresh_cron)

        publish = (role / "tasks" / "publish.yaml").read_text(encoding="utf-8")
        self.assertIn("Ensure infra-stats publish directories exist", publish)
        self.assertIn("infra_stats_scrape_dir", publish)
        self.assertIn("infra_stats_html_dir", publish)
        self.assertIn("publish_context.json.j2", publish)
        self.assertIn("refresh-infra-stats.sh", publish)
        self.assertIn('src: "{{ role_path }}/templates/stats.html.j2"', publish)
        self.assertIn("ansible.builtin.copy:", publish)
        self.assertIn("infra_stats_cert_paths", publish)
        self.assertIn("setup_custom_content_nginx", publish)
        self.assertIn("registry_tls_enabled", publish)
        self.assertIn("pkg_repo_tls_enabled", publish)
        self.assertIn("helm_repo_tls_enabled", publish)
        self.assertIn("custom_nginx_tls_enabled", publish)
        self.assertIn("bind_apex_static_records_harbor", publish)
        self.assertIn("INFRA_STATS_GENERATED_BY", publish)
        self.assertNotIn("import_tasks: scrape.yaml", publish)
        self.assertNotIn("infra-stats-vhosts.conf.j2", publish)
        # Host HTML must stay raw Jinja for Python refresh (not Ansible-rendered).
        html_deploy = publish.split("Deploy infra-stats HTML Jinja template")[-1].split(
            "Write infra-stats publish context"
        )[0]
        self.assertIn("ansible.builtin.copy:", html_deploy)
        self.assertNotIn("ansible.builtin.template:", html_deploy)

        render = (role / "tasks" / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("infra_stats_publish_source: compose_render", render)
        self.assertIn("import_tasks: publish.yaml", render)
        self.assertIn("refresh_infra_stats.py.j2", render)
        self.assertIn("refresh-infra-stats.sh.j2", render)
        self.assertIn("infra-stats-refresh.cron.j2", render)
        self.assertIn("python3-jinja2", render)
        self.assertIn("infra_stats_refresh_cron_enabled", render)
        self.assertIn('src: "{{ role_path }}/templates/stats.html.j2"', render)
        self.assertIn("Deploy raw infra-stats HTML Jinja template", render)
        # Refresh cron must be installed only after first publish (context on disk).
        self.assertLess(
            render.index("import_tasks: publish.yaml"),
            render.index("infra-stats-refresh.cron.j2"),
        )
        mark_when = render.split("Mark registry nginx stack pending restart")[-1]
        self.assertIn("infra_stats_vhosts_deployed.changed", mark_when)
        self.assertIn("infra_stats_tls_cert_issued.changed", mark_when)
        self.assertNotIn("infra_stats_html_deployed.changed", mark_when)
        self.assertNotIn("infra_stats_json_deployed.changed", mark_when)
        self.assertNotIn("infra_stats_issue_script_deployed.changed", mark_when)
        self.assertNotIn("register: infra_stats_html_deployed", render)
        self.assertNotIn("register: infra_stats_json_deployed", render)

        teardown = (role / "tasks" / "teardown.yaml").read_text(encoding="utf-8")
        self.assertIn("infra-stats-refresh", teardown)
        self.assertIn("refresh-infra-stats.sh", teardown)
        self.assertIn("refresh_infra_stats.py", teardown)
        self.assertIn("publish_context.json", teardown)
        self.assertIn("templates/stats.html.j2", teardown)
        self.assertIn("refresh-infra-stats.lock", teardown)

        pre_start = (role / "tasks" / "pre_start.yaml").read_text(encoding="utf-8")
        self.assertIn("import_tasks: issue_tls.yaml", pre_start)
        self.assertIn("infra_stats_publish_source: compose_start_registry", pre_start)
        self.assertIn("import_tasks: publish.yaml", pre_start)

        html = (role / "templates" / "stats.html.j2").read_text(encoding="utf-8")
        json_tmpl = (role / "templates" / "stats.json.j2").read_text(encoding="utf-8")
        self.assertNotIn("ansible_date_time", html)
        self.assertNotIn("ansible_date_time", json_tmpl)
        self.assertIn("runtime writer: refresh_infra_stats.py", json_tmpl)
        self.assertIn("generated_by", json_tmpl)
        self.assertIn("infra_stats_publish_source", json_tmpl)
        self.assertIn("bind_scrape_ok", json_tmpl)
        self.assertIn("ntp_scrape_ok", json_tmpl)
        self.assertIn("known_scrape_ok", json_tmpl)
        self.assertIn("issued_scrape_ok", json_tmpl)
        self.assertIn("issued_annotate_ok", json_tmpl)
        self.assertIn("bind_scrape_stale", json_tmpl)
        self.assertIn("ntp_scrape_stale", json_tmpl)
        self.assertIn("known_scrape_stale", json_tmpl)
        self.assertIn("issued_scrape_stale", json_tmpl)
        self.assertIn("cache_scrape_ok", json_tmpl)
        self.assertIn("cache_scrape_stale", json_tmpl)
        self.assertIn("cache", json_tmpl)
        self.assertIn("docker_hub", json_tmpl)
        self.assertIn("\"ca\"", json_tmpl)
        self.assertIn("ntp", json_tmpl)
        self.assertIn("issued_certs", json_tmpl)
        self.assertIn("infra_stats_issued_certs", html)
        self.assertIn("Certificates issued by step-ca", html)
        self.assertIn("<h2>NTP</h2>", html)
        self.assertIn("infra_stats_ntp_scrape_ok", html)
        self.assertIn("infra_stats_ntp_scrape_stale", html)
        self.assertIn("setup_ntp", html)
        self.assertIn("chronyc", html)
        self.assertIn("margin: 0 auto", html)
        self.assertIn("text-align: center", html)
        self.assertIn("| e", html)
        self.assertIn("on disk", html)
        self.assertIn("db only", html)
        self.assertIn("on_disk", html)
        self.assertIn("generated_by", html)
        self.assertIn("Published via <span class=\"mono\">{{ generated_by }}</span>", html)
        self.assertNotIn("infra_stats_publish_source", html)
        self.assertIn("stale", html)
        self.assertIn("scrape failed", html)
        self.assertIn("annotate failed", html)
        self.assertIn("previous snapshot kept", html)
        self.assertIn("infra_stats_known_scrape_ok", html)
        self.assertIn("infra_stats_issued_scrape_ok", html)
        self.assertIn("infra_stats_issued_annotate_ok", html)
        self.assertIn("infra_stats_bind_scrape_ok", html)
        self.assertIn("infra_stats_bind_scrape_stale", html)
        self.assertIn("infra_stats_known_scrape_stale", html)
        self.assertIn("infra_stats_issued_scrape_stale", html)
        self.assertIn("<h2>Infra cache</h2>", html)
        self.assertIn("infra_stats_cache_scrape_ok", html)
        self.assertIn("infra_stats_cache_scrape_stale", html)
        self.assertIn("infra_stats_cache", html)
        self.assertIn("KEY:", html)
        self.assertIn("Trust / CA", html)
        self.assertIn("/ca/roots.pem", html)
        self.assertIn("install-root-ca-debian.sh", html)
        self.assertIn("install-root-ca-rhel.sh", html)
        self.assertIn("infra_stats_docker_hub", html)
        self.assertIn("Hub pulls left", html)


        issue = (role / "tasks" / "issue_tls.yaml").read_text(encoding="utf-8")
        self.assertIn("Re-check infra-stats TLS files after issue", issue)
        self.assertIn("item.stat.exists", issue)

        reg_compose = (
            REPO_ROOT
            / "roles"
            / "07-deploy-registry-nginx-compose"
            / "templates"
            / "docker-compose.yml.j2"
        ).read_text(encoding="utf-8")
        reg_nginx = (
            REPO_ROOT / "roles" / "07-deploy-registry-nginx-compose" / "templates" / "nginx.conf.j2"
        ).read_text(encoding="utf-8")
        reg_render = (
            REPO_ROOT / "roles" / "07-deploy-registry-nginx-compose" / "tasks" / "render.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("setup_infra_stats", reg_compose)
        self.assertIn("infra-stats-vhosts", reg_compose)
        self.assertIn("infra_stats_html_dir", reg_compose)
        self.assertIn("infra-stats-vhosts/infra-stats-vhosts.conf", reg_nginx)
        self.assertIn("infra-stats-vhosts.stub.j2", reg_render)

        bind_render = (
            REPO_ROOT / "roles" / "03-deploy-bind-compose" / "tasks" / "render.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("bind_apex_stats_dns_records", bind_render)
        self.assertIn("setup_infra_stats", bind_render)

        playbook = (REPO_ROOT / "playbooks" / "infra_hosts.yaml").read_text(encoding="utf-8")
        self.assertIn("13_deploy_infra_stats", playbook)
        self.assertIn("13-deploy-infra-stats", playbook)

        docs = (REPO_ROOT / "docs" / "infra-stats.md").read_text(encoding="utf-8")
        self.assertIn("setup_infra_stats", docs)
        self.assertIn("always clears", docs)
        self.assertIn("skipped", docs)
        self.assertIn("folded into `issued_scrape_ok`", docs)
        self.assertIn("*_scrape_stale", docs)
        self.assertIn("issued_annotate_ok", docs)
        self.assertIn("non-empty", docs)
        self.assertIn("setup_ntp", docs)
        self.assertIn("chronyc", docs)
        self.assertIn("ntp.json", docs)
        self.assertIn("cache.json", docs)
        self.assertIn("Cache inventory", docs)
        self.assertIn("KEY:", docs)
        self.assertIn("helm-releases", docs)
        self.assertIn("/stats", docs)
        self.assertIn("/ca/roots.pem", docs)
        self.assertIn("install-root-ca-debian.sh", docs)
        self.assertIn("ratelimitpreview/test", docs)
        self.assertIn("compose_render", docs)
        self.assertIn("compose_start_registry", docs)
        self.assertIn("publish.yaml", docs)
        self.assertIn("topo-sorted", docs)
        self.assertIn("atomic", docs)
        self.assertIn("stale", docs)
        self.assertIn("on_disk", docs)
        self.assertIn("does **not**", docs)
        self.assertIn("cron-refresh", docs)
        self.assertIn("infra_stats_refresh_cron", docs)
        self.assertIn("flock", docs)
        self.assertIn("role_path", docs)
        self.assertIn("raw", docs)
        self.assertNotIn("dnsdomainname", docs)

        stacks_defaults = (
            REPO_ROOT / "roles" / "06-enable-compose-systemd" / "defaults" / "main.yml"
        ).read_text(encoding="utf-8")
        infra_stats_block = stacks_defaults.split("- id: infra_stats\n", 1)[1].split(
            "\n  - id:", 1
        )[0]
        self.assertIn("after:\n      - registry\n", infra_stats_block)
        self.assertIn("- registry_nginx\n", infra_stats_block)
        self.assertIn("- pkg_repo_nginx\n", infra_stats_block)
        self.assertIn("- helm_repo_nginx\n", infra_stats_block)
        self.assertIn("- custom_nginx\n", infra_stats_block)
        self.assertIn("pre_start:\n      - pre_start.yaml\n", infra_stats_block)

    def test_infra_cache_seed_contract(self) -> None:
        catalog = (REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.yml").read_text(
            encoding="utf-8"
        )
        secrets_overlay = (REPO_ROOT / "group_vars" / "all" / "atlas-infra-edge.secrets.yml").read_text(
            encoding="utf-8"
        )
        playbook = (REPO_ROOT / "playbooks" / "infra_hosts.yaml").read_text(encoding="utf-8")
        role = REPO_ROOT / "roles" / "14-infra-cache-seed"
        validate = (REPO_ROOT / "roles" / "01_validate_vars" / "tasks" / "cache_seed.yml").read_text(
            encoding="utf-8"
        )
        defaults = (role / "defaults" / "main.yml").read_text(encoding="utf-8")
        load = (role / "tasks" / "load.yaml").read_text(encoding="utf-8")
        publish = (role / "tasks" / "publish.yaml").read_text(encoding="utf-8")
        dockerfile = (role / "templates" / "Dockerfile.j2").read_text(encoding="utf-8")
        extract = (role / "templates" / "extract.sh.j2").read_text(encoding="utf-8")
        main = (role / "tasks" / "main.yaml").read_text(encoding="utf-8")
        write_stamp = (role / "tasks" / "write_stamp.yaml").read_text(encoding="utf-8")
        check_stamp = (role / "tasks" / "check_stamp.yaml").read_text(encoding="utf-8")
        components = (role / "tasks" / "components.yaml").read_text(encoding="utf-8")
        staging = (role / "tasks" / "build_staging.yaml").read_text(encoding="utf-8")
        stop_services = (role / "tasks" / "stop_services.yaml").read_text(encoding="utf-8")
        restart_services = (role / "tasks" / "restart_services.yaml").read_text(encoding="utf-8")
        validate_disk = (role / "tasks" / "validate_disk.yaml").read_text(encoding="utf-8")
        assert_stopped = (role / "tasks" / "assert_services_stopped.yaml").read_text(
            encoding="utf-8"
        )
        assert_started = (role / "tasks" / "assert_services_started.yaml").read_text(
            encoding="utf-8"
        )
        assert_one_started = (role / "tasks" / "assert_one_started.yaml").read_text(
            encoding="utf-8"
        )

        self.assertTrue((role / "tasks" / "load.yaml").is_file())
        self.assertTrue((role / "tasks" / "publish.yaml").is_file())
        self.assertTrue((role / "tasks" / "load_services_hold.yaml").is_file())
        self.assertTrue((role / "tasks" / "assert_services_stopped.yaml").is_file())
        self.assertTrue((role / "tasks" / "assert_services_started.yaml").is_file())
        self.assertTrue((role / "tasks" / "assert_one_started.yaml").is_file())
        self.assertTrue((role / "README.md").is_file())
        self.assertIn("Refuse bare include of 14-infra-cache-seed", main)
        self.assertIn("infra_cache_seed_publish_enabled: false", catalog)
        self.assertIn("infra_cache_seed_load_enabled: false", catalog)
        self.assertIn("infra_cache_seed_builder_image: busybox:1.36", catalog)
        self.assertIn("infra_cache_seed_publish_include:", catalog)
        self.assertIn("infra_cache_seed_load_include:", catalog)
        self.assertIn("infra_cache_seed_registry_tls_ca_enabled: false", catalog)
        self.assertIn("infra_cache_seed_registry_tls_ca_src: \"\"", catalog)
        self.assertIn("infra_cache_seed_registry_tls_ca_dir: \"\"", catalog)
        self.assertIn("infra_cache_seed_registry_tls_ca_validate_certs: false", catalog)
        self.assertNotIn("infra_cache_seed_publish_registry_password:", catalog)
        self.assertNotIn("infra_cache_seed_load_registry_user:", catalog)
        self.assertIn("infra_cache_seed_publish_registry_user:", secrets_overlay)
        self.assertIn("infra_cache_seed_load_registry_password:", secrets_overlay)
        self.assertIn("CHANGEME", secrets_overlay)
        self.assertIn("cannot both", validate)
        self.assertIn("infra_cache_seed_load_enabled", validate)
        self.assertIn("nginx_cache_sync_enabled", validate)
        self.assertIn("not latest", validate)
        self.assertIn("is boolean", validate)
        self.assertIn("infra_cache_seed_registry_tls_ca_enabled", validate)
        self.assertIn("infra_cache_seed_registry_tls_ca_src", validate)
        self.assertIn("infra_cache_seed_registry_tls_ca_dir", validate)
        self.assertIn("exactly one of", validate)
        self.assertIn("14-infra-cache-seed", playbook)
        self.assertIn("tasks_from: load.yaml", playbook)
        self.assertIn("tasks_from: publish.yaml", playbook)
        self.assertIn("not (infra_cache_seed_load_enabled", playbook)
        self.assertIn("compose_timing_phase: 14_infra_cache_seed_load", playbook)
        self.assertIn("compose_timing_phase: 14_infra_cache_seed_publish", playbook)
        self.assertLess(
            playbook.index("Load infra cache seed image (before registry start)"),
            playbook.index("Pull infra cache mirror from remote (before registry start)"),
        )
        self.assertLess(
            playbook.index("Pull infra cache mirror from remote (before registry start)"),
            playbook.index("Compose start registry group"),
        )
        self.assertLess(
            playbook.index("Push infra cache mirror to remote (after compose reconcile)"),
            playbook.index("Publish infra cache seed image (after compose reconcile)"),
        )
        self.assertIn("infra_cache_seed_publish_enabled: false", defaults)
        self.assertIn("cache-seed.stamp", defaults)
        self.assertIn("infra_cache_seed_registry_tls_ca_enabled: false", defaults)
        self.assertIn("infra_cache_seed_registry_tls_ca_src: \"\"", defaults)
        self.assertIn("infra_cache_seed_registry_tls_ca_dir: \"\"", defaults)
        self.assertTrue((role / "tasks" / "registry_ca.yaml").is_file())
        registry_ca = (role / "tasks" / "registry_ca.yaml").read_text(encoding="utf-8")
        self.assertIn("/etc/docker/certs.d/", registry_ca)
        self.assertIn("playbook_dir", registry_ca)
        self.assertIn("*.pem", registry_ca)
        self.assertIn("get_url", registry_ca)
        self.assertIn("remote_src: true", registry_ca)
        self.assertIn("docker", load)
        self.assertIn("registry_ca.yaml", load)
        self.assertLess(load.index("registry_ca.yaml"), load.index("login.yaml"))
        self.assertIn("registry_ca.yaml", publish)
        self.assertLess(publish.index("registry_ca.yaml"), publish.index("login.yaml"))
        self.assertIn("extract.yaml", load)
        self.assertIn("write_stamp.yaml", load)
        self.assertIn("load_services_hold.yaml", load)
        self.assertIn("RepoDigests", load)
        self.assertIn("assert_services_stopped.yaml", load)
        self.assertIn("fix_ownership.yaml", load)
        self.assertIn("imagetools", load)
        self.assertIn("sha256:[0-9a-f]{64}", load)
        self.assertIn("\n              - du\n", load)
        self.assertIn("\n              - -sb\n", load)
        self.assertIn("-sb", load)
        self.assertIn("/seed", load)
        self.assertLess(load.index("imagetools"), load.index("Pull infra cache seed image"))
        self.assertLess(load.index("imagetools"), load.index("\n              - du\n"))
        self.assertLess(load.index("load_services_hold.yaml"), load.index("check_stamp.yaml"))
        self.assertLess(load.index("check_stamp.yaml"), load.index("Pull infra cache seed image"))
        pull_block = load.split("name: Pull infra cache seed image\n", 1)[1]
        self.assertIn("check_stamp.yaml", pull_block)
        self.assertNotIn("not (infra_cache_seed_remote_digest_ok", pull_block)
        self.assertLess(load.index("fix_ownership.yaml"), load.index("restart_services.yaml"))
        self.assertLess(load.index("write_stamp.yaml"), load.index("restart_services.yaml"))
        self.assertIn("always:", load)
        self.assertIn("build_argv.yaml", publish)
        self.assertIn("build_staging.yaml", publish)
        self.assertIn("assert_services_stopped.yaml", publish)
        self.assertIn("infra_cache_seed_seed_bytes: 0", publish)
        self.assertIn("Infra cache seed publish cleanup", publish)
        self.assertLess(publish.index("Infra cache seed publish cleanup"), publish.index("logout.yaml"))
        self.assertIn("'digest':", write_stamp)
        self.assertIn("'components':", write_stamp)
        self.assertNotIn('components: "{{', write_stamp)
        self.assertIn("RepoDigests", check_stamp)
        self.assertIn("dest_empty", check_stamp)
        self.assertIn('find "$dest" -type f -print -quit', check_stamp)
        self.assertNotIn("-mindepth 1", check_stamp)
        self.assertIn("sha256:[0-9a-f]{64}", check_stamp)
        self.assertIn("digest_ids", check_stamp)
        self.assertIn("localhost", components)
        self.assertIn("load_services_hold.yaml", stop_services)
        self.assertIn("state: absent", restart_services)
        self.assertIn("assert_services_started.yaml", restart_services)
        self.assertIn("infra_cache_seed_started_ok", restart_services)
        self.assertLess(
            restart_services.index("assert_services_started.yaml"),
            restart_services.index("state: absent"),
        )
        self.assertIn("or (infra_cache_seed_started_ok", restart_services)
        self.assertIn("dest_need", validate_disk)
        self.assertIn("work_need", validate_disk)
        self.assertIn("64 * 1024 * 1024", validate_disk)
        self.assertIn("infra_cache_seed_seed_bytes", validate_disk)
        self.assertNotIn("infra_cache_seed_image_size", validate_disk)
        self.assertNotIn(".Size", validate_disk)
        dest_checks = [
            line
            for line in validate_disk.splitlines()
            if "item.host_dir" in line and "check_path" in line
        ]
        work_checks = [
            line
            for line in validate_disk.splitlines()
            if "infra_cache_seed_work_dir" in line and "check_path" in line
        ]
        self.assertEqual(len(dest_checks), 1, dest_checks)
        self.assertEqual(len(work_checks), 1, work_checks)
        self.assertIn("$dest_need", dest_checks[0])
        self.assertNotIn("$work_need", dest_checks[0])
        self.assertIn("$work_need", work_checks[0])
        self.assertNotIn("$dest_need", work_checks[0])
        self.assertIn("default(1)", assert_stopped)
        self.assertIn("infra_cache_seed_assert_ps.rc", assert_stopped)
        self.assertIn("assert_one_started.yaml", assert_started)
        self.assertIn("refusing to clear the hold", assert_started)
        self.assertIn("infra_cache_seed_started_ok: true", assert_started)
        self.assertIn("docker compose ps -q", assert_one_started)
        self.assertIn("infra_cache_seed_started_ps.rc", assert_one_started)
        self.assertIn("RemainAfterExit", assert_one_started)
        self.assertNotIn("not (setup_compose_systemd", assert_one_started)
        self.assertIn("== 'active'", assert_one_started)
        self.assertIn("--exclude=certs", dockerfile)
        self.assertIn("/seed/registry", dockerfile)
        self.assertIn("/seed/helm-releases", dockerfile)
        self.assertIn("COPY --from=helm_releases", dockerfile)
        self.assertIn("COPY helm-releases /seed/helm-releases", dockerfile)
        self.assertIn("/seed/MANIFEST", dockerfile)
        self.assertIn("'seed_dir': 'helm-releases'", components)
        self.assertIn("host_dir': helm_repo_nginx_releases_dir", components)
        self.assertIn(
            "{% if not (infra_cache_seed_publish_use_staging | default(false) | bool) %}",
            dockerfile,
        )
        self.assertIn("# syntax=docker/dockerfile:1.7", dockerfile)
        staging_if = dockerfile.split(
            "{% if infra_cache_seed_publish_use_staging | default(false) | bool %}", 1
        )[1]
        staging_branch = staging_if.split("{% else %}", 1)[0]
        self.assertNotIn("# syntax=docker/dockerfile:1.7", staging_branch)
        self.assertIn('DOCKER_BUILDKIT: "0"', staging)
        self.assertIn("du -sb", staging)
        self.assertIn("cp -a /seed/", extract)
        self.assertNotIn("certs", extract)
        readme = (role / "README.md").read_text(encoding="utf-8")
        self.assertIn("XOR", readme)
        self.assertIn("external", readme.lower())
        self.assertIn("RepoDigest", readme)
        self.assertIn("default playbook/orchestrator slot", readme)
        self.assertIn("./run.sh", readme)
        self.assertIn("untagged", readme)
        self.assertIn("**push**", readme)
        self.assertIn("imagetools inspect", readme)
        self.assertIn("regular file", readme)
        self.assertIn("sha256", readme)
        self.assertIn("RemainAfterExit", readme)
        self.assertIn("/seed/helm-repo", readme)
        self.assertIn("/seed/helm-releases", readme)
        self.assertIn("helm_repo_nginx_releases_dir", readme)

    def test_no_tracked_pycache(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "*__pycache__*", "*.pyc"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(tracked.returncode, 0)
        self.assertEqual(tracked.stdout.strip(), "", tracked.stdout)


if __name__ == "__main__":
    unittest.main()
