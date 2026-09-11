"""Helm chart repo URL helpers for infra nginx compose (none | nexus | nginx)."""

import re
from urllib.parse import urlparse


def _slug(value):
    slug = re.sub(r"[^a-zA-Z0-9._-]", "-", value or "")
    return slug.replace(".", "-")


def _upstream_parts(upstream_url):
    parsed = urlparse((upstream_url or "").rstrip("/"))
    return {
        "origin": f"{parsed.scheme}://{parsed.netloc}",
        "path_prefix": parsed.path or "",
    }


# Extra chart download hosts for GitHub Releases pull-through (index → github.com → redirect).
GITHUB_RELEASES_CHART_HOST = "release-assets.githubusercontent.com"


class FilterModule(object):
    def filters(self):
        return {
            "helm_repo_proxy_hostname": self.helm_repo_proxy_hostname,
            "helm_repo_nginx_origin": self.helm_repo_nginx_origin,
            "helm_repo_nginx_path_prefix": self.helm_repo_nginx_path_prefix,
            "helm_repo_chart_hosts": self.helm_repo_chart_hosts,
        }

    def helm_repo_proxy_hostname(self, name, ingress_domain):
        return f"{_slug(name)}.{ingress_domain}"

    def helm_repo_nginx_origin(self, upstream_url):
        return _upstream_parts(upstream_url)["origin"]

    def helm_repo_nginx_path_prefix(self, upstream_url):
        return _upstream_parts(upstream_url)["path_prefix"]

    def helm_repo_chart_hosts(self, upstream_host, chart_hosts=None):
        """Extra chart download hosts for index.yaml URL rewrite (beyond upstream_host)."""
        hosts = [h for h in (chart_hosts or []) if h]
        if not hosts and (upstream_host or "").endswith(".github.io"):
            hosts = ["github.com"]
        if "github.com" in hosts and GITHUB_RELEASES_CHART_HOST not in hosts:
            hosts.append(GITHUB_RELEASES_CHART_HOST)
        seen = set()
        deduped = []
        for host in hosts:
            if host not in seen:
                seen.add(host)
                deduped.append(host)
        return deduped
