# Infra stats page (`stats.<dns>/stats`)

Static HTML + JSON summary of lab infra (nginx locations, apt/yum/helm/docker repos,
on-disk cache inventory, BIND zone scrape, NTP compose chronyc, known on-disk CA/leaf
TLS certs, and step-ca issued certs from the badger DB). Served from **shared
registry-nginx** — no dedicated compose unit.

## Enable

```yaml
setup_infra_stats: true
```

Leaf `dev/infra` sets this. Requires `setup_registry_nginx` and `setup_stepca` (for
`infra_stats_tls_enabled`).

## URLs

- `https://stats.<dns_domain_suffix>/stats` — HTML
- `https://stats.<dns_domain_suffix>/stats.json` — machine-readable snapshot
- `https://stats.<dns_domain_suffix>/` — `302` → `/stats`
- `https://stats.<dns_domain_suffix>/ca/roots.pem` — lab step-ca root (copy from disk)
- `https://stats.<dns_domain_suffix>/ca/install-root-ca-debian.sh` — Debian/Ubuntu trust install
- `https://stats.<dns_domain_suffix>/ca/install-root-ca-rhel.sh` — RHEL/OL trust install

Auth: none (lab HTTPS / CA trust only). First CA download needs `curl -k` until the
root is in the client store.

The HTML page uses operator tabs (Trust, Endpoints, Mirrors, Cache, DNS, Time,
TLS) on a black background. Hash `#trust` … `#tls` is sticky; nested hashes
like `#mirrors/apt` and `#cache/overview` remember the inner tab.

**Mirrors** has inner tabs: APT / YUM, Helm repos, Docker / registry.
**Cache** has Overview plus one inner tab per on-disk tree (APT/YUM metadata
and blobs, Helm repos/releases, Docker/registry, custom www).

Root CA PEM, Debian/Ubuntu, RHEL/OL, and JSON live on the **Trust / CA** tab:
one button per row with a short description. Install scripts `curl -k` the PEM
from `/ca/roots.pem`, then `update-ca-certificates` or `update-ca-trust extract`.
Nginx `server_names` and proxy hosts are `https://` links (wildcard names stay
plain text).

**Docker Hub pulls left** (anonymous `HEAD` of `ratelimitpreview/test`) is the Hub
quota for this host's WAN IP — the same pool pull-through uses. Docker documents
that this check does not consume a pull. Snapshot is in `stats.json` as `docker_hub`.

## Render / scrape

Role `13-deploy-infra-stats` publishes via `tasks/publish.yaml`: Ansible builds a
static **`publish_context.json`**, copies the **raw** Jinja
`stats.html.j2` to the host (`copy` + `role_path`, not Ansible `template`), then
runs host-side `refresh-infra-stats.sh` → `refresh_infra_stats.py` (scrape +
Jinja2 HTML/JSON). Only Python renders the page.

Ansible triggers that refresh on:

1. **`compose_render`** (or legacy tag `13_deploy_infra_stats` / `infra_stats` /
   `deploy_infra_stats`) — after optional TLS issue when step-ca is already
   provisioned. Stacks are **topo-sorted** by `after[]` (same as start), so
   `infra_stats` runs after peer TLS leaves when those stacks are enabled. Sets
   `infra_stats_publish_source=compose_render`.
2. **`compose_start_registry` pre_start** — after deferred TLS issue for
   infra-stats. Pre-start hooks are also topo-sorted; `infra_stats` depends on
   `registry`, `registry_nginx`, `pkg_repo_nginx`, `helm_repo_nginx`, and
   `custom_nginx`. Sets `infra_stats_publish_source=compose_start_registry`.

`stats.json` field `generated_by` is `ansible-compose_render`,
`ansible-compose_start_registry`, or **`cron-refresh`**.

### Periodic refresh cron

Independent of TLS renew. Default every 10 minutes (`infra_stats_refresh_cron_*`):

```yaml
infra_stats_refresh_cron_enabled: true
infra_stats_refresh_cron_minute: "*/10"
infra_stats_refresh_cron_hour: "*"
infra_stats_refresh_cron_dom: "*"
infra_stats_refresh_cron_month: "*"
infra_stats_refresh_cron_dow: "*"
infra_stats_refresh_cron_log_file: /var/log/infra-stats-refresh.log
```

Cron reuses the last Ansible `publish_context.json` (nginx/pkg/helm rows stay until
the next Ansible publish) and re-scrapes BIND/NTP/certs/cache. Overlap is prevented with
`flock`. Requires `python3-jinja2` on the host.

`compose_reconcile` only applies pending registry-nginx restarts; it does **not**
refresh HTML/JSON. Cron **TLS** renew (`infra-stats-tls-renew`) also does **not**
re-publish the page — only the refresh cron (or Ansible publish) does.

It writes:

- `/opt/infra-stats/html/stats.html`
- `/opt/infra-stats/html/stats.json`
- `/opt/infra-stats/conf/vhosts/infra-stats-vhosts.conf` (render only)
- scrape intermediates under `/opt/infra-stats/scrape/` (not served by nginx)
- `/opt/infra-stats-compose/publish_context.json` + refresh scripts

BIND records are parsed from `/opt/bind/zones/*.db` when `setup_bind`; otherwise the
page falls back to apex/static inventory records.

NTP (when `setup_ntp`): `docker exec {{ ntp_container_name }} chronyc -c
tracking|sources` plus a running-container check. Snapshot is a one-element JSON
list (summary + nested sources) for the same soft-fail nonempty-list contract as
BIND/certs. Tracking CSV supports chrony ≤4.5 (13 cols) and ≥4.6 (14 cols with
reference name/IP after RefID).

Certificates:

- **Known leaves + CA chain** — `openssl x509` on on-disk paths for stacks with
  both the setup gate and TLS enabled.
- **Issued by step-ca** — DER scan of `/opt/stepca/db` (`*.vlog` + `*.sst`). All
  found serials are listed; `on_disk: true` marks overlap with known present
  leaves (annotated in Python after both JSON files exist).

Scrape writes are **atomic** (`*.json.tmp` then `os.replace`). Orphan
`*.json.tmp` files are removed at the start of each scrape; Python dump paths also
`unlink` tmp in `finally` if replace did not run.

Gate-off (`setup_bind` / `setup_ntp` / `setup_stepca` false) **always clears** the
matching JSON to `[]` and keeps `*_scrape_ok: true` (intentional empty). Annotate is
**skipped** when step-ca is off or issued scrape soft-failed, so gate-off ok is
never flipped by a bad `certs.json`.

BIND / NTP / known / issued scrapes **soft-fail** when the gate is on: on failure a
previous **non-empty** snapshot is kept (`*_scrape_stale`); missing, empty `[]`,
or corrupt JSON is replaced with `[]` (not stale). When issued scrape succeeds,
`on_disk` annotate runs and is folded into `issued_scrape_ok` (annotate fail →
ok false, no stale). HTML: **stale** (kept snapshot), **annotate failed**
(on_disk not refreshed), or **scrape failed** (empty). `stats.json` exposes
`*_scrape_ok`, `*_scrape_stale`, `ntp`, `cache`, and `issued_annotate_ok`.

Cache inventory (always scraped when the page is published):

- **pkg-metadata / pkg-blobs** and **helm-repo** — nginx `proxy_cache` files. Names
  come from the `KEY:` header (host+URI). That is **not** an apt/helm catalog; a
  URI may include a version (`kubelet_1.36.3-1.1_amd64.deb`) when the upstream
  path does.
- **helm-releases** — real paths under `helm_repo_nginx_releases_dir`.
- **registry** — per-upstream size plus `name:tag` from
  `docker/registry/v2/repositories/**/_manifests/tags/` (`certs/` skipped).
- **custom-www** — top-level dest dirs/files (e.g. `external-snapshotter/v8.6.0`).

HTML lists newest objects first, up to `infra_stats_cache_html_limit` (default 200)
per tree. `stats.json` keeps up to `infra_stats_cache_json_limit` (default 2000).
Missing dirs are `present: false`, not a scrape failure. Trees whose `setup_*`
gate is off are omitted.

Scrape intermediates:
`/opt/infra-stats/scrape/{certs,issued_certs,bind_zones,ntp,cache}.json`
(including `ntp.json` when `setup_ntp` and `cache.json` for the inventory).

## Manual check

Substitute your leaf `dns_domain_suffix`:

```bash
curl --cacert /opt/stepca/certs/root_ca.crt \
  "https://stats.<dns_domain_suffix>/stats"

# Force refresh without waiting for cron:
/opt/infra-stats-compose/refresh-infra-stats.sh
```
