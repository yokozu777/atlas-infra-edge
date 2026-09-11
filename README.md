# atlas-infra-edge

Ansible playbooks for the **infra platform node**: Docker CE, compose systemd units, BIND, NTP, step-ca, registry / nginx pull-through caches, and optional cache sync between peers.

**Canonical playbook:** `playbooks/infra_hosts.yaml`  
**Runner:** `./run.sh`  
**Vars catalog:** `group_vars/all/atlas-infra-edge.yml`  
**Secrets overlay:** `group_vars/all/atlas-infra-edge.secrets.yml`  
**Package repo mirrors:** [`docs/pkg-repos.md`](docs/pkg-repos.md) (upstream Host/SNI here;
client contract + official URL catalog in sibling `atlas-node-foundation`)  
**Infra stats page:** [`docs/infra-stats.md`](docs/infra-stats.md) (`stats.<dns>/stats` on shared registry-nginx)  
**License:** Apache-2.0 (see `LICENSE`)

```
  ./run.sh
      |
      v
  validate (localhost) --> Docker CE on infra_platform
      |
      v
  compose unit files --> BIND / NTP / step-ca --> registry (+ nginx)
      |
      v
  pkg / helm / custom nginx caches --> (cache pull) --> systemd reconcile --> (cache push)
```

Clients / cluster nodes later use this host for DNS, CA, and pull-through mirrors.
Optional orchestrated path: phase `infra` after host init (inventory + group_vars from an external controller).

## Compatibility

Targeted at:
- **Ubuntu** / **Debian** (Docker CE apt)
- **Oracle Linux** / RHEL-family (Docker CE dnf; `firewalld` as needed)

Inventory contract (required group — override the name via vars if needed):

| Group (default) | Targeting var | Role |
|-----------------|---------------|------|
| `infra_platform` | `infra_platform_hosts` | Docker engine + gated compose stacks (must be non-empty) |

Prefer a stable per-host `hostname:` (FQDN) when BIND / TLS SANs need a predictable name.

To use a different inventory group name:

```yaml
# group_vars/all/atlas-infra-edge.yml
infra_platform_hosts: my_infra_nodes
```

OS bootstrap (users, base packages, host CA trust) is **out of scope** of this repository — provide a reachable Linux baseline first. Sibling repos often used for that path: compute provisioning + node OS-init; this playbook only installs Docker and the gated edge compose stacks on the platform host.

## Quickstart

### Prerequisites

- Ansible 2.14+ recommended
- `ansible-galaxy collection install -r requirements.yml` (`ansible.posix`)
- SSH access to the infra host (Python 3 on the target)
- Replace every `CHANGEME` **before** enabling secrets-backed gates (`setup_bind`, `setup_stepca`, cache sync password auth, …)
- Prefer Ansible Vault / `EXTRA_VARS_FILE` for secrets (see `examples/secrets.example.yml`)
- Outbound (or mirrored) access for Docker CE packages when `use_internal_rpm_apt_repo: none`

### Clone

```bash
git clone <atlas-infra-edge-url>
cd atlas-infra-edge
ansible-galaxy collection install -r requirements.yml
```

### Inventory

```bash
cp inventory-example.yml inventory.yml
vi inventory.yml
```

Set `ansible_host` (and preferably `hostname:`) on every host in the group named by `infra_platform_hosts` (default `infra_platform`).

### Variables

**SoT:** `group_vars/all/atlas-infra-edge.yml` — full standalone catalog (same surface as orchestrated `atlas-infra-edge.yml`): **REQUIRED** workspace / targeting, **OPTIONAL** gates, pull modes, BIND/NTP/CA/registry/pkg+helm caches, upstream maps.
Role `defaults/` still apply for any unset key; standalone keeps gates off and pull modes `none` until you enable them.

Standalone defaults keep pull modes at `none` and most compose gates **off**, so a first run can install Docker without BIND/TSIG/step-ca:

```yaml
use_internal_rpm_apt_repo: none
use_internal_docker_registry: none
use_internal_helm_repo: none
setup_bind: false
setup_ntp: false
setup_stepca: false
setup_compose_systemd: true
nginx_cache_sync_enabled: false
```

When enabling BIND / step-ca, fill secrets (or supply via vault overlay).
Secrets feed `bind_zones.*.tsig_secret` via the flat placeholders below:

```yaml
bind_apex_tsig_secret: "CHANGEME"
bind_k8s_tsig_secret: "CHANGEME"
bind_istio_tsig_secret: "CHANGEME"
stepca_init_password: "CHANGEME"
```

Authoritative zones are declared once as `bind_zones` (logical id → zone). Default
catalog ships `apex` / `k8s` / `istio` under `dns_domain_suffix` — no
`k8s_cluster_domain` required. Add more keys without editing role templates.

```bash
cp examples/secrets.example.yml ~/infra-edge-secrets.yml
# edit, optionally: ansible-vault encrypt ~/infra-edge-secrets.yml
EXTRA_VARS_FILE=~/infra-edge-secrets.yml ./run.sh
```

### Run

```bash
./run.sh --tags 00_ensure_workspace         # localhost workspace only
./run.sh --tags 01_validate_vars            # inventory targeting contract (localhost)
./run.sh                                    # full play = Phase 3 cold path (per gates)
./run.sh --tags compose_render
./run.sh --tags compose_pull
./run.sh --tags compose_start_core
./run.sh --tags compose_start_registry
./run.sh --tags compose_reconcile
./run.sh --tags 03_deploy_bind_compose      # legacy single-stack (explicit only)
./run.sh --check -v
```

`00_ensure_workspace` runs on localhost when selected (`tags: 00_ensure_workspace`); external orchestrators typically invoke it first explicitly.  
Remote plays keep tags on roles / `include_role` only (no play-level role-tag union — that
would re-run every compose task on each `--tags`). Workspace / validate-only skips SSH because
untagged remote tasks are skipped under `--tags`.

`ansible.cfg` enables jsonfile fact caching so cacheable `set_fact` values (for example
`pkg_repo_cache_warm_pending` between deploy → sync pull → reconcile) survive split
`--tags` runs. `./run.sh` points the cache at `<workspace>/.ansible_facts_cache`.

Or manually:

```bash
ansible-playbook -i inventory.yml playbooks/infra_hosts.yaml
```

### `./run.sh` environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `INVENTORY` | `inventory.yml` or `inventory-example.yml` | Inventory path |
| `PLAYBOOK` | `playbooks/infra_hosts.yaml` | Playbook path |
| `EXTRA_VARS_FILE` | — | Optional `-e @file` (vaulted secrets) |
| `SSH_KEY` / `ANSIBLE_PRIVATE_KEY_FILE` | `~/.ssh/id_ed25519` or `id_rsa` | SSH private key |
| `CLUSTER_WORKSPACE_ID` | `infra.example.com` | Workspace directory name under parent |
| `CLUSTER_WORKSPACE_PARENT` | `./workspace` (absolute under repo in `./run.sh`) | Parent directory for workspaces |
| `CLUSTER_WORKSPACE_ROOT` | `<parent>/<id>` | Full controller workspace path |
| `ANSIBLE_CONFIG` | `./ansible.cfg` | Ansible config |
| `ANSIBLE_CACHE_PLUGIN_CONNECTION` | `<workspace>/.ansible_facts_cache` | Fact cache directory (jsonfile) |

All extra CLI arguments are forwarded to `ansible-playbook`.

## Architecture (role order)

`playbooks/infra_hosts.yaml` (high level):

```
  ensure_workspace --> validate --> (skip previews)
         |
         v
  bootstrap_repos --> docker --> daemon
         |
         v
  compose_render --> compose_pull --> compose_start_core
         |
         v
  cache_fill --> compose_start_registry (+ warm) --> reconcile --> cache_push
```

1. **00_ensure_workspace** (localhost, tag `00_ensure_workspace`) — resolve `CLUSTER_WORKSPACE_*`, create controller workspace dirs  
2. **01_validate_vars** (localhost) — inventory group, DNS identity, pull-mode / derived-gate consistency, feature-gated secrets (rejects `CHANGEME` when gates are on)  
3. **Skip previews** (localhost, tag `00_ensure_workspace`) — debug messages when feature gates are off  
4. **Docker play** (`{{ infra_platform_hosts }}`) — bootstrap public package repos → install Docker CE → configure daemon/containerd  
5. **Compose play** (`{{ infra_platform_hosts }}`) — teardowns → compose_render → compose_pull → compose_start_core → cache fill (rsync **xor** OCI seed) → compose_start_registry → reconcile → cache push / optional seed publish  

Feature gates (`setup_bind`, `setup_ntp`, …) control which compose stacks run; Docker engine roles always run when the playbook is invoked.

| Tag (primary) | Role / stage | Gate |
|---------------|--------------|------|
| `00_bootstrap_infra_repos` | `00-bootstrap-infra-repos` | `infra_bootstrap_public_pkg_repos` |
| `01_install_docker_engine` | `01-install-docker-engine` | (always) |
| `02_configure_docker_daemon` | `02-configure-docker-daemon` | (always) |
| `compose_render` | `06-enable-compose-systemd` (units + render) | `setup_compose_systemd` |
| `compose_pull` | `06-enable-compose-systemd` (image pull) | `setup_compose_systemd` |
| `compose_start_core` | start BIND/NTP/step-ca | `setup_compose_systemd` |
| `11_sync_infra_cache_pull` / `_push` | `11-sync-infra-cache` | `nginx_cache_sync_enabled` |
| `14_infra_cache_seed_load` / `_publish` | `14-infra-cache-seed` | `infra_cache_seed_load_enabled` / `infra_cache_seed_publish_enabled` |
| `compose_start_registry` | start registry/nginxes + warm | `setup_compose_systemd` |
| `compose_reconcile` | `06-enable-compose-systemd` (slim reconcile) | `setup_compose_systemd` |

Typical flow on the platform host:

```
  bootstrap_repos --> install_docker --> configure_daemon
         |
         v
  compose_render --> compose_pull --> compose_start_core
         |
         v
  cache_fill --> compose_start_registry (+ warm) --> reconcile --> cache_push
```

Filter plugins (`filter_plugins/pkg_repo.py`, `helm_repo.py`, `registry_mirror.py`) resolve public vs mirror URIs for package / Helm / registry modes.

## Compose stack catalog (`infra_compose_stacks`)

Declarative SoT for every gated compose stack lives in
`roles/06-enable-compose-systemd/defaults/main.yml` (`infra_compose_stacks`).
See also `roles/06-enable-compose-systemd/README.md`.

Phase 0–5: catalog is the SoT; builders and phase tasks consume it via
`filter_plugins/compose_stacks.py`. Each deploy role exposes `tasks/render.yaml`
(files only) and a **thin** `main.yaml` (`import_tasks: render.yaml`; step-ca also
imports `bootstrap.yaml`). The playbook cold path is the phase sequence. Per-role
image pulls are gone — only `compose_pull` pulls. External orchestrators that split
`--tags` per phase should use the same phase tag order as this playbook. CI
(`tests/test_compose_stack_registry.py`, `tests/test_compose_stacks_filter.py`)
enforces parity, topo-sort, thin mains, and the render contract.

| `start_group` | Stacks | Cold-path rule |
|---------------|--------|----------------|
| `core` | bind, ntp, stepca | May start before cache fill (`11_sync_infra_cache_pull` xor `14_infra_cache_seed_load`) |
| `registry` | registry, registry_nginx, pkg/helm/custom nginx, infra_stats | Must not start until after cache fill |

**Contract (do not violate when adding stacks):**

- **render** — templates / files / unit deploy / `mark_pending` only; never `docker pull`, stack start, or `warm_cache`  
- **pull** — unique images once (skip-if-present); not inside render  
- **reconcile** — pending restarts only; no full image re-pull  

**Phase 3–6 cold path** (default untagged / `--tags all`; also split orchestrator plans):

| Tag | Role tasks_from |
|-----|-----------------|
| `compose_render` | units + loop render (+ teardowns for disabled stacks) |
| `compose_pull` | unique skip-if-present pull (**parallel** by default) |
| `compose_start_core` | topo-sorted start BIND/NTP/step-ca |
| `11_sync_infra_cache_pull` | rsync cache pull (does not start registry if it was not up) |
| `14_infra_cache_seed_load` | OCI seed extract onto `/opt` bind-mounts (XOR with rsync pull) |
| `compose_start_registry` | topo-sorted start registry/nginxes + warm |
| `compose_reconcile` | slim reconcile (also `06_enable_compose_systemd_reconcile`) |
| `11_sync_infra_cache_push` | cache push |
| `14_infra_cache_seed_publish` | pack `/opt` into an OCI seed and `docker push` (rare donor; opt-in `--tags`, not a default play slot) |

Phase 6: `compose_pull_parallel: true` by default; set `false` to serialise pulls.
Duration lines `atlas_infra_edge_timing phase=… duration_s=…` when
`compose_timing_enabled` (default true). Air-gapped hosts may `docker load` images
before `compose_pull` — skip-if-present then no-ops network pulls.
Legacy per-role deploy tags remain for single-stack **render** ops (`main.yaml` =
`render.yaml`); they do not pull/start on their own. Use `compose_pull` /
`compose_start_*` / `compose_reconcile` (or a full play) to apply runtime.

### Adding a compose stack

1. Role under `roles/` with thin `tasks/main.yaml` → `render.yaml` (+ optional hooks).
2. Entry in `infra_compose_stacks` (`start_group`, `after`, gates) — see
   `roles/06-enable-compose-systemd/README.md`.
3. Optional legacy `--tags 0X_deploy_*` include in `playbooks/infra_hosts.yaml`
   (renders only; does not pull/start).
4. Layout / catalog tests + this README.

**External orchestrators do not need a new invocation** — `compose_render` /
`compose_pull` / `compose_start_*` / `compose_reconcile` already cover catalog stacks.

Flat inventory knobs (`*_image`, `*_compose_project_dir`, `compose_systemd_*_unit_name`) remain the operator overrides; the catalog only names those variables.

## Feature gates and pull modes

| Knob | Standalone default | Meaning |
|------|--------------------|---------|
| `setup_bind` / `setup_ntp` / `setup_stepca` | `false` | Compose stacks (secrets required for BIND / step-ca); BIND zones via `bind_zones` dict |
| `ntp_disable_host_chrony` | `true` | When NTP compose is enabled: stop/**mask** host chrony so it cannot reclaim UDP/123 or fight `CAP_SYS_TIME`. Pair with foundation `ntp_manage_host_chrony: false` on the NTP leaf (init-infra-post). |
| `setup_compose_systemd` | `true` | systemd units + reconcile for compose projects |
| `use_internal_rpm_apt_repo` | `none` | Legacy label only; does **not** derive `setup_apt_rpm_nginx`. Client path uses leaf `pkg_repos`. |
| `use_internal_helm_repo` | `none` | `none` / `nexus` / `nginx` |
| `use_internal_docker_registry` | `none` | `none` / `harbor` / `registry` |
| `setup_pkg_repo_nginx` / `setup_helm_repo_nginx` / `setup_custom_nginx` | `false` | Explicit nginx ingress enables |
| `setup_infra_stats` | `false` | Static `/stats` page on shared registry-nginx |
| `nginx_cache_sync_enabled` | `false` | On-demand rsync mirror between peers |

Derived flags (do not fight them unless you know why):

- `setup_registry` / `setup_registry_nginx` ← `use_internal_docker_registry == 'registry'`
- `setup_apt_rpm_nginx` ← `setup_pkg_repo_nginx` (Phase 3 infra-local mirror gate)
- `setup_helm_nginx` ← `use_internal_helm_repo == 'nginx' and setup_helm_repo_nginx`
- `setup_custom_content_nginx` ← `get_snapshotter == 'internal-nginx' and setup_custom_nginx`

## Greenfield checklist

1. Infra host is reachable over SSH; Python 3 present.  
2. `inventory.yml` has a non-empty group named by `infra_platform_hosts` (default `infra_platform`).  
3. `group_vars/all/atlas-infra-edge.yml` workspace / `dns_domain_suffix` / `dns_server_ip` look right.  
4. Decide which gates to enable; fill every `CHANGEME` for those stacks (or `EXTRA_VARS_FILE`).  
5. `./run.sh --tags 00_ensure_workspace` succeeds (controller workspace under `./workspace/`).  
6. `./run.sh --tags 01_validate_vars` succeeds.  
7. `./run.sh --tags 01_install_docker_engine` installs Docker CE.  
8. Enable gates; run phase tags (`compose_render` → `compose_pull` → `compose_start_core`
   → cache pull → `compose_start_registry` → `compose_reconcile`) or a full `./run.sh`.  
9. Re-run `./run.sh` — expect idempotent no-op for unchanged config.  
10. Optional: enable `nginx_cache_sync_*` only when a peer host and SSH auth are ready.

## Troubleshooting

### `01_validate_vars` fails on inventory group

Ensure the inventory defines a non-empty group whose name matches `infra_platform_hosts` (default `infra_platform`). When renaming the group, update both the inventory and `infra_platform_hosts` (and any orchestrator `--limit`).

### `01_validate_vars` fails on CHANGEME / pull modes

- Enabling `setup_bind` / `setup_stepca` (or cache sync password auth) requires real secrets — placeholders are rejected.  
- Enabling `use_internal_*` / `get_snapshotter=internal-nginx` requires matching `setup_*` flags, domains, TLS, and non-empty upstream/mirror lists.  
- Do not manually override derived flags (`setup_registry`, `setup_apt_rpm_nginx`, …).

### Workspace role fails on directory create

Ensure `CLUSTER_WORKSPACE_*` / `cluster_domain` resolve to a writable path under the repo (or an absolute path you own). `./run.sh` absolutizes relative parents against the repository root.

### Docker CE install fails

- Mode `none`: host needs access to public Docker package repos.  
- Mode `nexus` / `nginx`: set matching `nexus_base_url` / `pkg_repo_nginx_ingress_domain` and ensure the mirror publishes the containerd/Docker slugs.  
- Oracle: confirm `firewalld` / SELinux knobs (`disable_selinux`) match site policy.

### BIND / step-ca assert on secrets

Do not leave `CHANGEME` when `setup_bind` or `setup_stepca` is true. Prefer vaulted `EXTRA_VARS_FILE` (`examples/secrets.example.yml`).

### Registry nginx requires backends

`setup_registry_nginx` needs `setup_registry=true` and non-empty registry proxy upstreams (usually from `use_internal_docker_registry: registry` + role 05). Deploy registry compose before registry-nginx.

### TLS roles require step-ca

Registry / pkg / helm / custom nginx TLS paths assert `setup_stepca=true` and a
provisioned step-ca marker before issuing certs. ACME scripts use
`pki_ca_host` (catalog default `ca.{{ dns_domain_suffix }}`, aligned with
`stepca_init_dns_names`) — distinct from node-foundation `pki_ca_url` (roots.pem
trust-store list).

### Cache sync cannot SSH

Check `nginx_cache_sync_remote_host`, auth mode (`key` vs `password`), and that the private key / password is supplied. See `roles/11-sync-infra-cache/README.md`.

### SSH host key changed after VM recreate

```bash
ssh-keygen -f ~/.ssh/known_hosts -R '192.0.2.10'
```

## Testing / CI

Local checks (same gates as GitHub Actions):

```bash
./tests/run_ci.sh
# or piecemeal:
python3 -m unittest discover -s tests -p 'test_*.py' -v
ansible-playbook --syntax-check -i inventory-example.yml playbooks/infra_hosts.yaml
ansible-lint --profile min
./scripts/check-no-hardcoded-domains.sh
./run.sh --tags 00_ensure_workspace
./run.sh --tags 01_validate_vars
```

CI workflow: `.github/workflows/ci.yml` (unit tests, syntax-check, ansible-lint `min`, domain scan, publish hygiene).

Optional stricter lint locally: `ansible-lint --profile basic` (style findings; not a merge gate yet).

Lab / live idempotency helpers are **not** part of `./tests/run_ci.sh` / GHA.

Layout / fingerprint suite: `tests/test_infra_edge_layout.py`.  
Compose stack registry / parity suite: `tests/test_compose_stack_registry.py`.  
Compose stack filter unit tests: `tests/test_compose_stacks_filter.py`.  
Filter unit tests: `tests/test_pkg_repo_filter.py`.

## Project structure

```
atlas-infra-edge/
├── playbooks/
│   └── infra_hosts.yaml
├── docs/
│   ├── pkg-repos.md
│   └── infra-stats.md
├── run.sh
├── ansible.cfg
├── requirements.yml
├── inventory-example.yml
├── group_vars/
│   └── all/
│       └── atlas-infra-edge.yml
├── examples/
│   └── secrets.example.yml
├── host_vars/
│   └── example.yml
├── filter_plugins/
│   ├── pkg_repo.py
│   ├── helm_repo.py
│   ├── registry_mirror.py
│   └── compose_stacks.py
├── roles/
│   ├── 00_ensure_workspace/
│   ├── 01_validate_vars/
│   ├── 00-bootstrap-infra-repos/
│   ├── 01-install-docker-engine/
│   ├── 02-configure-docker-daemon/
│   ├── 03-deploy-bind-compose/
│   ├── 04-deploy-stepca-compose/
│   ├── 05-deploy-registry-compose/
│   ├── 06-enable-compose-systemd/   # infra_compose_stacks catalog + units/reconcile
│   ├── 07-deploy-registry-nginx-compose/
│   ├── 08-deploy-pkg-repo-nginx-compose/
│   ├── 09-deploy-helm-repo-nginx-compose/
│   ├── 10-deploy-custom-nginx-compose/
│   ├── 11-sync-infra-cache/
│   ├── 12-deploy-ntp-compose/
│   └── 13-deploy-infra-stats/
├── scripts/
│   └── check-no-hardcoded-domains.sh
├── tests/
│   ├── run_ci.sh
│   ├── test_infra_edge_layout.py
│   ├── test_compose_stack_registry.py
│   ├── test_compose_stacks_filter.py
│   └── test_pkg_repo_filter.py
├── .github/workflows/ci.yml
├── .ansible-lint
├── requirements-dev.txt
├── LICENSE
└── SECURITY.md
```

## Integrations

External orchestrators can call the same playbook with their own inventory and group/host vars. Set the inventory group (or override `infra_platform_hosts`) and knobs from `group_vars/all/atlas-infra-edge.yml` (feature gates, pull modes, DNS identity, secrets).

Suggested tag sequence for split runs: workspace → validate → Docker install/configure → compose deploy tags in playbook order → reconcile → optional cache sync.

Org-specific lab overlays (domains, mirrors, TSIG, step-ca passwords, peer sync endpoints) belong in the orchestrator inventory — not in this repository’s defaults.

## Security

See [`SECURITY.md`](SECURITY.md) for reporting, secret-handling, fingerprint guards, and the pre-publish git history note. Do not commit real credentials, vault files, or live inventories (`inventory.yml` and local workspace paths are gitignored). Licensed under [Apache-2.0](LICENSE).

## Contributing

1. Keep `playbooks/infra_hosts.yaml` as the only supported playbook entry.  
2. Document new operator-facing variables in `group_vars/all/atlas-infra-edge.yml` and role `defaults/`.  
3. When adding a compose stack: update `infra_compose_stacks`, keep `build_compose_*.yaml` in parity, extend registry + layout tests.  
4. Extend `tests/test_infra_edge_layout.py` / `tests/test_compose_stack_registry.py` (and filter tests) for layout/contract changes.  
5. Keep `./tests/run_ci.sh` green before opening a PR.  
6. Update this README when behaviour, tags, gates, or inventory contracts change.  
7. Keep product sources free of org lab hostnames and non-English operator-facing copy.

## Support

Open an issue in the repository for bugs and questions.
