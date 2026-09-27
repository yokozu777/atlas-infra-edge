# 14-infra-cache-seed

Pack infra pull-through caches from host bind-mounts into an OCI image (donor)
and extract selected trees onto a cold consumer **before** registry start.

This is **not** a fat `registry-nginx` / `registry-proxy-*` image. Cache lives on
the host (`/opt/...`); the seed image is a one-shot `docker run --rm` copy.

## Layers

| Layer | Flag | When | Transport |
|-------|------|------|-----------|
| publish | `infra_cache_seed_publish_enabled` | after `compose_reconcile` (rare donor) | `docker push` to an **external** registry |
| load | `infra_cache_seed_load_enabled` | after `compose_start_core`, before `compose_start_registry` | `docker pull` + extract |

Credentials live in `atlas-infra-edge.secrets.yml` (two robot accounts).
Load user/password may both be empty for an anonymous pull (public Docker Hub);
private registries still need a robot. Publish still requires push creds.
Tags must be immutable (not `latest`).

**XOR:** `infra_cache_seed_load_enabled` and `nginx_cache_sync_enabled` cannot both
be true (`01_validate_vars`). Choose seed load **or** role-11 rsync on a leaf.
Publish may run on a donor that also 11-pushes.

Chicken-egg: the seed registry must be reachable while only core stacks (Docker /
BIND / NTP / step-ca) are up. Do not store the seed in the Harbor this leaf is
bootstrapping.

Private CA for that **external** registry (login / pull / push) is optional
`infra_cache_seed_registry_tls_ca_*`. When enabled, the role writes
`/etc/docker/certs.d/<registry-host>/ca.crt` before `docker login` (no dockerd
restart, not the OS trust store, not `insecure-registries`). XOR one source:
`infra_cache_seed_registry_tls_ca_src` (HTTP(S) URL fetched on the host, or a
file already on the host) **or** `infra_cache_seed_registry_tls_ca_dir` (folder
relative to `playbook_dir` on the controller; all `.crt`/`.pem` concatenated,
same idea as node-foundation `custom_certs_dir`). URL fetch uses
`infra_cache_seed_registry_tls_ca_validate_certs` (default false, same as
foundation `ca_certificate_validate_certs`).

TLS under `registry_data_dir/certs` is never packed.

Standalone `./run.sh` (untagged) and `--tags all` **push** when
`infra_cache_seed_publish_enabled=true`. Split `--tags 14_infra_cache_seed_load`
does not publish. Publish is **not** a default playbook/orchestrator slot after
reconcile (that slot is `11_sync_infra_cache_push`) — donor hosts use
`--tags 14_infra_cache_seed_publish`. `--tags 14_infra_cache_seed` with **both**
layer flags true runs load and publish in one play.

The builder `infra_cache_seed_builder_image` (`busybox:1.36`) must exist on the
donor (`docker pull` or preload). A site overlay may pin a digest.

## Image layout

| Path | Host dest |
|------|-----------|
| `/seed/registry` | `registry_data_dir` (no `certs/`) |
| `/seed/helm-repo` | `helm_repo_nginx_cache_dir` |
| `/seed/helm-releases` | `helm_repo_nginx_releases_dir` |
| `/seed/pkg-repo` | `pkg_repo_nginx_cache_dir` |
| `/seed/custom-www` | `custom_nginx_www_dir` |
| `/seed/MANIFEST` | one component name per line |

Load include may be a subset of published components; missing dirs fail extract.
`helm_repo: true` publishes and loads **both** `helm-repo` (proxy_cache) and
`helm-releases` (GitHub Releases file store).

## Tags

```bash
# Cold-path load (also runs on untagged all when load_enabled)
ansible-playbook playbooks/infra_hosts.yaml --limit infra_platform \
  -e @group_vars/all/atlas-infra-edge.secrets.yml \
  --tags 14_infra_cache_seed_load

# Donor publish (opt-in tag; not a default play slot)
ansible-playbook playbooks/infra_hosts.yaml --limit infra_platform \
  -e @group_vars/all/atlas-infra-edge.secrets.yml \
  --tags 14_infra_cache_seed_publish
```

Canonical cold path:

```
compose_start_core
  → 14_infra_cache_seed_load  XOR  11_sync_infra_cache_pull
  → compose_start_registry
  → compose_reconcile
  → 11_sync_infra_cache_push
# optional donor, not a default play slot:
  → --tags 14_infra_cache_seed_publish
```

Load skips extract when `infra_cache_seed_load_skip_if_same_digest` is true, the
stamp already records the same **sha256** as the remote manifest (`docker buildx
imagetools inspect`, no layer pull; compare the digest id, not `name@digest`),
the component set matches, and every dest tree contains a regular file (empty
directory skeletons do not skip). Imagetools stdout that is not `sha256:<64 hex>`
is ignored (same as missing buildx). After a pull, stamp is compared again
against local `RepoDigests` so a registry-name prefix mismatch does not recopy
`/opt`. A tag match alone is not enough; wiping `/opt` while leaving the stamp
forces extract. Hold is cleared only after held compose projects show running
containers (`docker compose ps`; systemd `RemainAfterExit` is not enough).
Nginx cache/www trees are chowned to `infra_cache_seed_nginx_uid/gid`
(official nginx alpine = 101:101). Registry blobs stay root (`COPY` +
`registry:3.1.1`). Site images that drop privileges need an overlay uid.

Publish prefers BuildKit additional contexts (no extra disk copy; needs the
`docker/dockerfile:1.7` frontend). If that fails, it rsyncs enabled trees into
`infra_cache_seed_work_dir` (certs excluded) and builds with the classic builder
(`DOCKER_BUILDKIT=0`, no `# syntax=` line).
