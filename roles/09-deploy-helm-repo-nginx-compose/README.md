# 09-deploy-helm-repo-nginx-compose

Helm chart, GitHub raw, Grafana gnet, and GitHub Releases ingress on nginx.

## GitHub Releases file store

Clients keep stable URLs (`releases.helm.<leaf>/org/repo/releases/download/...` and
chart-vhost `/@chart/github.com/...`). GitHub answers 302 to signed
`release-assets.githubusercontent.com` URLs (SAS). Those query strings must not
enter `proxy_cache`.

| Outcome | Behavior |
|---------|----------|
| HIT | `try_files` serves a file under `helm_repo_nginx_releases_dir` (`X-Cache-Status: STORE`) |
| MISS online | named location `proxy_pass https://github.com` (and SAS location); `proxy_cache off` |
| MISS offline | 404 until warm/seed fills the store |

Do **not** use `proxy_store` (it would persist the 302 HTML). Vhost change still
wipes `helm_repo_nginx_cache_dir` only.

Fill the store with `--tags helm_repo_cache_warm`:

- `helm_repo_cache_warm_specs` — chart `.tgz` via the helm mirror (`proxy_cache`); GitHub chart URLs are written to the same releases store from `github.com`
- `helm_repo_releases_warm_specs` — explicit github.com paths (`curl -L` / urllib follow SAS, then GET `releases.<leaf>/<path>` must be 200 without `Location`)

Seed load / role-11 rsync with `helm_repo: true` copies **two** trees: `helm-repo` and `helm-releases`.
