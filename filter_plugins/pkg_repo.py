"""APT/RPM repo URL helpers for infra nginx compose (none | nexus | nginx)."""

import re
from urllib.parse import urlparse

_PUBLIC_BY_SLUG = {
    "debian-main": "https://deb.debian.org/debian",
    "debian-security": "https://deb.debian.org/debian-security",
    "debian-non-free": "https://deb.debian.org/debian",
    "ubuntu": "https://archive.ubuntu.com/ubuntu",
    "pgdg-apt": "https://apt.postgresql.org/pub/repos/apt",
    "pgdg-yum": "https://download.postgresql.org/pub/repos/yum",
    "debian-containerd": "https://download.docker.com/linux/debian",
    "ubuntu-containerd": "https://download.docker.com/linux/ubuntu",
    "yum_docker-ce-stable-9": "https://download.docker.com/linux/centos/9/x86_64/stable",
    "yum_docker-ce-stable-10": "https://download.docker.com/linux/centos/10/x86_64/stable",
    "gitlab-runner-ubuntu": "https://packages.gitlab.com/runner/gitlab-runner/ubuntu",
    "gitlab-runner-debian": "https://packages.gitlab.com/runner/gitlab-runner/debian",
    "gitlab-runner-el": "https://packages.gitlab.com/runner/gitlab-runner/el/9/x86_64",
}


def _slug(value):
    slug = re.sub(r"[^a-zA-Z0-9._-]", "-", value or "")
    return slug.replace(".", "-")


def _public_uri(slug, pkg_repo_upstreams):
    for item in pkg_repo_upstreams or []:
        if item.get("slug") == slug:
            url = (item.get("upstream_url") or "").rstrip("/")
            if url:
                return url
    return _PUBLIC_BY_SLUG.get(slug, "")


def _upstream_parts(upstream_url):
    parsed = urlparse((upstream_url or "").rstrip("/"))
    return {
        "origin": f"{parsed.scheme}://{parsed.netloc}",
        "path_prefix": parsed.path or "",
    }


class FilterModule(object):
    def filters(self):
        return {
            "pkg_repo_proxy_hostname": self.pkg_repo_proxy_hostname,
            "pkg_repo_client_uri": self.pkg_repo_client_uri,
            "pkg_repo_nginx_origin": self.pkg_repo_nginx_origin,
            "pkg_repo_nginx_path_prefix": self.pkg_repo_nginx_path_prefix,
        }

    def pkg_repo_proxy_hostname(self, slug, ingress_domain):
        return f"{_slug(slug)}.{ingress_domain}"

    def pkg_repo_client_uri(
        self,
        slug,
        mode,
        nexus_base_url,
        nginx_ingress_domain,
        pkg_repo_upstreams=None,
    ):
        mode = (mode or "none").strip()
        slug = slug or ""
        public = _public_uri(slug, pkg_repo_upstreams)

        if mode == "none":
            return public
        if mode == "nexus":
            base = (nexus_base_url or "").rstrip("/")
            return f"{base}/{slug}" if base else public
        if mode == "nginx":
            domain = (nginx_ingress_domain or "").strip()
            if domain:
                return f"https://{_slug(slug)}.{domain}"
        return public

    def pkg_repo_nginx_origin(self, upstream_url):
        return _upstream_parts(upstream_url)["origin"]

    def pkg_repo_nginx_path_prefix(self, upstream_url):
        return _upstream_parts(upstream_url)["path_prefix"]
