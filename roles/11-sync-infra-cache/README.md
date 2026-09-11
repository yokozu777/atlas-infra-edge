# 11-sync-infra-cache

On-demand mirror of infra pull-through caches between hosts.

## What is synced

All data lives under a single remote root (`nginx_cache_sync_remote_dir`):

| Subdir | Local path | Content |
|--------|------------|---------|
| `pkg-repo/` | `pkg_repo_nginx_cache_dir` | APT/RPM nginx proxy_cache |
| `helm-repo/` | `helm_repo_nginx_cache_dir` | Helm charts proxy_cache |
| `helm-releases/` | `helm_repo_nginx_releases_dir` | GitHub Releases file store (`try_files`) |
| `registry/` | `registry_data_dir` (except `certs/`) | Docker registry layers |
| `custom-www/` | `custom_nginx_www_dir` | Static content for custom nginx |

Warm chart archives into `helm-repo/` and GitHub release binaries into
`helm-releases/` before air-gap platform runs:

```bash
ansible-playbook playbooks/infra_hosts.yaml --limit infra_platform \
  -e @group_vars/all/atlas-infra-edge.secrets.yml \
  --tags helm_repo_cache_warm
```

Specs: `helm_repo_cache_warm_specs` and `helm_repo_releases_warm_specs` in
group_vars / inventory (role `09-deploy-helm-repo-nginx-compose`).
`nginx_cache_sync_helm_repo_enabled` rsyncs both helm trees.

Registry TLS certs are **not** synced (`certs/` excluded).

## Examples

```bash
# Sync only registry layers (pull from donor host)
ansible-playbook playbooks/infra_hosts.yaml --limit infra_platform \
  -e @group_vars/all/atlas-infra-edge.secrets.yml \
  -e nginx_cache_sync_enabled=true \
  -e nginx_cache_sync_direction=pull \
  -e nginx_cache_sync_remote_host=192.0.2.10 \
  -e nginx_cache_sync_pkg_repo_enabled=false \
  -e nginx_cache_sync_helm_repo_enabled=false \
  -e nginx_cache_sync_custom_www_enabled=false \
  --tags 11_sync_infra_cache_pull
```

## Pull order (Phase 3)

After `pull` the role runs in this order:

1. **probe** (SSH / dirs / free space)
2. **freshness check** (`check_fresh`) — may set `nginx_cache_sync_skip_pull`
3. **stop** only nginx / registry units that are actually active
   (`nginx_cache_sync_stop_services`; skipped when fresh). Writes a host-local
   services hold so a failed rsync still restarts them (and the next sync can heal)
4. rsync mirror from remote → local disk (skipped when fresh)
5. restart **held / stopped** services (`restart_services` in `always`)
   (cold path: nothing was up and no hold → nothing is started here)
6. write local stamp when `skip_if_fresh` is enabled (after a real pull)
7. **defer pkg-repo metadata warm** when `setup_compose_systemd: true`
   (sets `pkg_repo_cache_warm_pending` in the fact cache — `cacheable: true`)
8. **pkg-repo metadata warm** inline only when `setup_compose_systemd: false`

Canonical cold path in `playbooks/infra_hosts.yaml`:

```
compose_start_core → 11_sync_infra_cache_pull xor 14_infra_cache_seed_load → compose_start_registry (+ warm)
  → compose_reconcile → 11_sync_infra_cache_push
# optional donor, not a default play slot: --tags 14_infra_cache_seed_publish
```

Warm runs on `compose_start_registry`; reconcile warms only if pending remains
(e.g. sync-only tag without a following start_registry).

## Notes

- `nginx_cache_sync_stop_services: true` (default) stops registry-nginx and registry
  proxies **only when they were running**; rsync aborts if any target container is
  still running after stop. A `cache-sync-services.held` marker records restart
  intent so a failed rsync (or the next sync) still brings those units back.
  Cold path with no hold does not start registry early.
- No `--delete`: incremental rsync only; stale files may remain on the receiver.
- DNS/vhost names should match between source and destination for nginx cache hits.

## Ownership after pull

After `rsync --numeric-ids`, nginx cache/www trees are `chown`'d to the nginx
runtime user. Resolve mode (`nginx_cache_sync_ownership_resolve`):

| Mode | Behavior |
|------|----------|
| `static` (default) | Use `nginx_cache_sync_nginx_uid` / `nginx_cache_sync_nginx_gid` (official `nginx:*-alpine` = `101:101`) |
| `container` | `docker exec` `id` from a running `registry_nginx_container_name` |
| `image` | Legacy ownership-image probe via `nginx_cache_sync_ownership_image` (slow; escape hatch only) |

Default `static` avoids a cold-path `docker run` just to learn uid/gid. Override the
numeric ids only if your registry-nginx image uses a non-standard nginx user.

## Skip if fresh (pull only)

When `nginx_cache_sync_skip_if_fresh: true`, the role compares a host-local stamp
(`nginx_cache_sync_stamp_path`) to a remote fingerprint **before** stop/rsync:

```text
if not skip_if_fresh → pull
elif no local stamp → pull
elif stamp age > fresh_max_age_hours → pull
elif stamp peer/components drifted → pull
elif remote fingerprint != stamp → pull
else → skip (no stop / rsync / ownership / post_sync start)
```

Fingerprint v1 is `sha256` over remote `du -sb` sizes of enabled components
(registry excludes `certs/`, matching rsync) plus peer host/port/dir metadata —
one SSH round-trip, no full rsync.

| Knob | Default | Notes |
|------|---------|-------|
| `nginx_cache_sync_skip_if_fresh` | `false` | Product always syncs; lab/CI may enable |
| `nginx_cache_sync_fresh_max_age_hours` | `24` | Force refresh even if sizes match |
| `nginx_cache_sync_stamp_path` | `/var/lib/atlas-infra/cache-sync.stamp` | Written only after a successful pull when skip is enabled |

Force a full pull by deleting the stamp, raising max age to expire it, or changing
remote content size. Skip is intentionally **off** in product defaults so cold
path parity stays predictable.

## Parallel rsync

When `nginx_cache_sync_parallel: true`, enabled components (+ registry) rsync in
batches of `nginx_cache_sync_parallel_jobs` via Ansible `async` (same flags as
serial: `-a --numeric-ids --partial`, optional `-z`, registry `--exclude=certs`).

| Knob | Default | Notes |
|------|---------|-------|
| `nginx_cache_sync_parallel` | `false` | Keep off until lab bench vs serial |
| `nginx_cache_sync_parallel_jobs` | `4` | Max concurrent rsyncs per batch (1–8) |
| `nginx_cache_sync_parallel_timeout_sec` | `7200` | Per-job async timeout |
| `nginx_cache_sync_parallel_poll_sec` | `5` | `async_status` poll interval |

Any job with `rc != 0` fails the play; `write_stamp` does not run, so skip-if-fresh
will not mark a partial mirror as fresh. Disk/SSH contention can make parallel
**slower** than serial — bench on the target hosts before enabling in lab.
