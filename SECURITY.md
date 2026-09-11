# Security

## Reporting

If you discover a security issue in this repository, please open a private report with the maintainers (do not file a public issue with exploit details or credentials).

## Secrets in this repo

Do **not** commit:

- BIND TSIG keys / DNS update secrets
- step-ca provisioner passwords or intermediate CA private keys
- registry / nginx basic-auth credentials
- SSH private keys used for infra cache sync
- deprecated monolithic `secrets.yml` / `*.vault` with live values
- live inventory with production hosts (`inventory.yml`, local `hosts`)

Prefer `group_vars/all/atlas-infra-edge.secrets.yml` with Ansible Vault (trackable; do **not** gitignore). Standalone operators may also use `EXTRA_VARS_FILE` / `examples/secrets.example.yml` **outside** the tree. A monolithic `secrets.yml` is deprecated and must not hold live credentials in git.


Tracked examples intentionally use inert placeholders only (`CHANGEME` in `group_vars/all/atlas-infra-edge.yml` and `examples/secrets.example.yml`).

## Git history note (pre-publish)

The initial tree (`e6501ad`) shipped a **dead, unused** static file
`roles/02-configure-docker-daemon/files/containerd_config.toml` with org package-mirror
hostnames (`nexus.mxhash.com`). Active installs use the Jinja template
`templates/containerd_config.toml.j2` (`{{ nexus_host }}`); the static file was never
referenced by role tasks. It is removed from the working tree in the hygiene cleanup;
the blob remains reachable in git history until history is rewritten.

The same tree also used `/var/lib/mxhash` as the default bootstrap state directory
(`infra_bootstrap_repo_state_dir`). Product defaults now use a neutral path; org lab
overlays belong in the orchestrator inventory, not in this repository’s defaults.

No embedded Gitea HTTPS credentials or lab passwords (`Welcomeback*`) were found in
reachable product history of this repository. Still assume any historical org hostname
blobs are undesirable on a public remote.

Product sources (`roles/`, `playbooks/`, `group_vars/`, examples, inventory example, runner)
must stay free of org hostnames, lab credentials, and non-English operator-facing copy.
Lab overlays belong in the orchestrator inventory, not in this repository’s defaults.

Guardrails: `scripts/check-no-hardcoded-domains.sh`, `tests/test_infra_edge_layout.py`
(fingerprint + Cyrillic + secret-material + orchestrator-path scans), and `./tests/run_ci.sh`
/ `.github/workflows/ci.yml`.

Before making this repository public:

1. Confirm no live secrets were ever pushed to remotes (rotate anything that might have been).
2. Rewrite history (`git filter-repo` / BFG) to purge org-hostname blobs, or publish from a
   fresh orphan branch that contains only the cleaned tree.
3. Assume historical blobs remain reachable until remotes are rewritten / force-replaced.
