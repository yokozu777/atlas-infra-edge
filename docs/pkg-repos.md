# Package repos (infra-edge)

Client enable/URI contract and official upstream URL catalog live in sibling
**atlas-node-foundation** (same org git hosting):

- `atlas-node-foundation/docs/pkg-repos-contract.md` — Phase 0–6 + Waves A–D
  (client `pkg_repos` + publish gates + greenfield checklist)
- `atlas-node-foundation/docs/pkg-repos-catalog.md` + `pkg-repos-catalog.yml` — official upstream URLs

## This repo’s responsibility

| Concern | Where |
|---------|--------|
| `pkg_repo_upstreams` (`slug`, `upstream_url`, `upstream_host`) | `group_vars/all/atlas-infra-edge.yml` |
| Nginx pkg-repo proxy (`Host` / SNI = `upstream_host`) | `roles/08-deploy-pkg-repo-nginx-compose` |
| Mirror enable gate | `setup_pkg_repo_nginx` → `setup_apt_rpm_nginx` (Phase 3) |
| Warm which upstreams to pull | inventory `enable_repo_*` (until a dedicated warm-schema migration) |
| Harbor (`harbor_host`) | Docker registry mirror — **not** apt/yum |

`slug` must equal client `pkg_repos[].name` from the foundation contract.

## Phase 3 notes

- `pgdg-apt` / `pgdg-yum` are in `pkg_repo_upstreams` (warm via `enable_repo_pgdg_apt` /
  `enable_repo_pgdg_yum`, or legacy `enable_repo_pgdg`).
- `gitlab-runner-ubuntu` / `gitlab-runner-debian` / `gitlab-runner-el` mirror
  packages.gitlab.com for `atlas-gitlab-runner` (warm via
  `enable_repo_gitlab_runner_*`; client drop-ins are written by the product role,
  not foundation `pkg_repos`).
- **Redirect cache:** pkg-repo nginx must not cache HTTP `301`/`302`. Upstream
  (especially packages.gitlab.com) often redirects package blobs to GCS **signed
  URLs** that expire (~24h). Omitting `302` from a long `proxy_cache_valid`
  line is **not** enough — nginx still caches redirects from `Cache-Control` /
  `Expires`. Role sets `proxy_cache_valid 301 302 0` and
  `proxy_ignore_headers Cache-Control Expires Set-Cookie` so only `200`/`206`
  bodies are cached. After changing this, purge the on-disk proxy cache (render
  already deletes cache on vhost change).
- Mirror deploy is **infra-local**: `setup_pkg_repo_nginx: true` enables the stack.
  `use_internal_rpm_apt_repo` is a legacy label only; it no longer derives
  `setup_apt_rpm_nginx`. Client URIs live on leaf `pkg_repos`.
- Warm-set guidance: inventory `enable_repo_*` ↔ foundation catalog
  `example_leaf_lists.infra_mirror_*`.
- Dead legacy path knobs `pkg_repo_managed_*` removed from product/inventory
  overlays (client drop-ins are catalog `name`-based on foundation).

## Phase 6 notes

- Drift gate (foundation `tests/test_pkg_repos_phase6.py`): every static
  `pkg_repo_upstreams` URL/host must match the catalog; every
  `infra_mirror: present` row must exist here.
- Client-path greps ban resurrecting `enable_repo_*` / `use_internal_rpm_apt_repo`
  on foundation / product overlays — **not** on this infra warm surface.
