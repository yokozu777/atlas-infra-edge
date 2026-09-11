"""Registry mirror proxy hostnames for infra nginx compose roles."""

import re


def _slug(dir_name):
    slug = re.sub(r"[^a-zA-Z0-9._-]", "-", dir_name or "")
    return slug.replace(".", "-")


class FilterModule(object):
    def filters(self):
        return {
            "registry_mirror_host": self.registry_mirror_host,
        }

    def registry_mirror_host(self, dir_name, ingress_domain):
        return f"{_slug(dir_name)}.{ingress_domain}"
