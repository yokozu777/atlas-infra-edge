# 06-enable-compose-systemd

Deploys systemd units for gated docker-compose stacks, pulls images (skip-if-present),
and reconciles pending restarts. Pending restarts are tracked in the Ansible fact
cache so split `--tags` runs still converge.

## Compose stack catalog (`infra_compose_stacks`)

**SoT:** `defaults/main.yml` → `infra_compose_stacks`.

Runtime project/image lists are derived by `filter_plugins/compose_stacks.py`:

- `compose_stacks_to_projects` → `build_compose_systemd_projects.yaml`
- `compose_stacks_to_images` → `build_compose_pre_pull_images.yaml`

Parity / contract tests: `tests/test_compose_stack_registry.py`,
`tests/test_compose_stacks_filter.py`.

### Phase 2–3 task entrypoints

| `tasks_from` | Tag | Purpose |
|--------------|-----|---------|
| `compose_render.yaml` | `compose_render` | units + loop `render.yaml` for enabled stacks |
| `compose_pull.yaml` | `compose_pull` | unique images, skip-if-present, parallel pull |
| `compose_start_group.yaml` | `compose_start_core` / `compose_start_registry` | topo-sorted start (+ pre_start/bootstrap/post_start/warm) |
| `compose_reconcile.yaml` / `reconcile.yaml` | `compose_reconcile` | pending restart + ensure started (**no** full re-pull) |
| `deploy_units.yaml` | (via compose_render) | unit files only |

Canonical cold path (full play / `--tags all`):

```
compose_render → compose_pull → compose_start_core
  → 11_sync_infra_cache_pull xor 14_infra_cache_seed_load → compose_start_registry → compose_reconcile
  → 11_sync_infra_cache_push
# optional donor, not a default play slot: --tags 14_infra_cache_seed_publish
```

`11-sync-infra-cache` / `14-infra-cache-seed` stop/restart only services that were actually running
(cold path does not start registry during cache fill). Seed load and rsync pull are XOR.

### Role task entrypoints (per deploy role)

| File | Purpose |
|------|---------|
| `tasks/render.yaml` | Templates / dirs / certs / compose files / `mark_pending` only |
| `tasks/main.yaml` | Phase 5 thin: `import_tasks: render.yaml` (+ step-ca `bootstrap.yaml`) |
| `tasks/pre_start.yaml` | Hooks before unit start (NTP) — via `compose_start_*` |
| `tasks/post_start.yaml` | Hooks after unit start — via `compose_start_*` |
| `tasks/bootstrap.yaml` | step-ca only: ACME mid-role start (never from render-only) |
| `tasks/apply_runtime.yaml` | Optional ad-hoc nginx reload/recreate (**not** imported by main) |
| `tasks/warm_cache.yaml` | Cache warm — never imported from render |

### Contract

| Phase | Allowed | Forbidden |
|-------|---------|-----------|
| **render** | templates, files, dirs, certs scripts, unit file deploy, `mark_pending` | `docker pull`, `systemctl start/restart` of stacks, `warm_cache`; hard-fail if step-ca ACME not done yet |
| **pull** | unique images once, skip-if-present | pull inside render |
| **start `core`** | bind → ntp → stepca (honour `after`) | starting `registry` group before cache pull on cold path |
| **cache pull** | `11_sync_infra_cache` pull or `14_infra_cache_seed_load` | requiring registry nginx already up for app-layer sync |
| **start `registry`** | TLS `pre_start` (shared sidecars included) → registry → nginxes (+ warm) | starting before cache pull / before step-ca on cold path |
| **reconcile** | pending restart only | full image re-pull of every stack |

`start_group: core` stacks may be up before cache fill (`11_sync_infra_cache_pull` xor `14_infra_cache_seed_load`).
`start_group: registry` stacks must wait until after that fill on a cold path.

### Adding a stack

1. Add a deploy role under `roles/` with `tasks/render.yaml` + thin `main.yaml`
   (`import_tasks: render.yaml` only; step-ca may also import `bootstrap.yaml`).
2. Append an entry to `infra_compose_stacks` (schema comments in `defaults/main.yml`).
3. Wire the role into `playbooks/infra_hosts.yaml` (legacy single-tag include if needed)
   and update layout / registry tests.
4. Document the tag and gate in the repository README.

**External orchestrators / inventory:** no new playbook-entry invocation — existing
`compose_render` / `compose_pull` / `compose_start_*` / `compose_reconcile` tags
cover catalog stacks. Keep orchestrator invocation lists in lockstep with this
playbook when changing phase order.

Flat inventory knobs (`*_image`, `*_compose_project_dir`, `compose_systemd_*_unit_name`)
remain the operator overrides; the catalog only names those variables.

Pull knobs: `compose_pull_force`, `compose_pull_parallel` (default **true**),
`compose_pre_pull_retries`, `compose_pre_pull_delay`, `compose_pull_async_timeout`.

Timing: `compose_timing_enabled` (default **true**) emits `atlas_infra_edge_timing
phase=… duration_s=…` for render / pull / start_* / reconcile (and cache pull/push
from the playbook). Set `compose_timing_enabled: false` to silence.

Optional offline preload: place images on the host (`docker load < tarball` / mirror)
before `compose_pull`; skip-if-present then avoids network pull. There is no automated
`docker load` phase — operators preload out of band when air-gapped.
