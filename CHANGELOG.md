# Changelog

## [Unreleased]

### Added

- `13-deploy-infra-stats`: host-side `refresh-infra-stats.sh` /
  `refresh_infra_stats.py` (scrape + Jinja2 render) shared by Ansible publish and
  cron. Default `infra_stats_refresh_cron_*` every 10 minutes
  (`*/10 * * * *`); `generated_by` is `cron-refresh` or `ansible-<source>`.
  TLS renew cron still does not refresh the page.

### Fixed

- `13-deploy-infra-stats`: deploy raw host `stats.html.j2` via `copy`/`role_path`
  (not Ansible `template`) so cron refresh re-renders BIND/NTP/certs; complete
  refresh-cron defaults in role `defaults/`; `flock -w 120` so publish waits on
  an in-flight cron scrape instead of failing immediately.
- `13-deploy-infra-stats`: refresh shell propagates flock/python exit codes
  (no longer swallows failures after `if !`); install refresh cron **after**
  first `publish.yaml` so context exists before the job can fire.
- `12-deploy-ntp-compose`: **mask** host chrony (not only stop+disable) when
  `ntp_disable_host_chrony` so `init-infra-post` / manual enable cannot fight
  the NTP compose unit for UDP/123 and system clock. Teardown unmasks before
  re-enable. Pair with foundation `ntp_manage_host_chrony: false` on infra NTP
  leaves.
- `13-deploy-infra-stats`: NTP section (gate `setup_ntp`) — scrape compose
  `chronyc -c tracking|sources` into `ntp.json`, soft-fail/stale like BIND,
  HTML + `stats.json` fields `ntp_scrape_ok` / `ntp_scrape_stale` / `ntp`.
- `13-deploy-infra-stats`: parse chronyc **4.6+** `tracking` CSV (14 fields:
  RefID + ref name/IP before stratum); older 13-field format still works.

### Changed (pkg repos — Phase 3)

- Added `pgdg-apt` / `pgdg-yum` to product `pkg_repo_upstreams` (+ inventory
  `ci/infra` / `dev/mxhash` copies); warm script covers PGDG suites / yum paths.
- Mirror enable is infra-local: `setup_apt_rpm_nginx: "{{ setup_pkg_repo_nginx }}"`
  (no longer derived from `use_internal_rpm_apt_repo`).
- Validate `01_validate_vars` pull_modes updated; gates in
  `tests/test_pkg_repos_phase3.py`.

### Changed (pkg repos — Phase 6)

- Publish close-out docs: Phase 0–6 contract linkage; warm stays on `enable_repo_*`.
  Drift/grep gates live in sibling `atlas-node-foundation` `tests/test_pkg_repos_phase6.py`.

### Fixed (pkg repos — Wave C)

- Removed unused `pkg_repo_managed_*` path knobs from product defaults.
- Clarified warm=`enable_repo_*` / client=`pkg_repos` comments; debian-non-free
  warm pulls contrib/non-free/non-free-firmware indexes in full mode.

### Changed (pkg repos — Wave D)

- Docs link post-Phase-6 Waves A–D hardening; client contract remains in
  sibling `atlas-node-foundation`.
