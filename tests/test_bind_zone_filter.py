"""Unit tests for filter_plugins/bind_zone.py."""

from __future__ import annotations

import base64
import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load():
    path = REPO_ROOT / "filter_plugins" / "bind_zone.py"
    spec = importlib.util.spec_from_file_location("bind_zone", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BIND = _load()

_ZONE_DUMP = """\
$TTL 86400
@	IN	SOA bind.dev-mxhash.com. hostmaster.dev-mxhash.com. (
		2026082701 ; serial
		3600 ; refresh
		1800 ; retry
		604800 ; expire
		86400 ) ; minimum

	IN	NS	bind.dev-mxhash.com.

bind	IN	A	192.168.1.219
k8s	IN	NS	bind.dev-mxhash.com.
kubelb	IN	A	192.168.1.210
grafana.dev-mxhash.com.	86400	IN	A	10.0.0.9
"""


class BindZoneFilterTests(unittest.TestCase):
    def test_parse_skips_soa_and_apex_ns_keeps_dynamic_a(self):
        recs = BIND.bind_parse_zone_records(_ZONE_DUMP, origin="dev-mxhash.com")
        names = {(r["name"], r["type"]) for r in recs}
        self.assertIn(("bind", "A"), names)
        self.assertIn(("k8s", "NS"), names)
        self.assertIn(("kubelb", "A"), names)
        self.assertIn(("grafana", "A"), names)
        self.assertNotIn(("", "NS"), names)

    def test_union_static_wins_preserves_rfc2136(self):
        static = [
            {"name": "bind", "type": "A", "rdata": "192.168.1.219"},
            {"name": "k8s", "type": "NS", "rdata": "bind.dev-mxhash.com."},
        ]
        merged = BIND.bind_union_zone_records(
            static, _ZONE_DUMP, origin="dev-mxhash.com"
        )
        by_key = {(r["name"], r["type"]): r["rdata"] for r in merged}
        self.assertEqual(by_key[("bind", "A")], "192.168.1.219")
        self.assertEqual(by_key[("kubelb", "A")], "192.168.1.210")
        self.assertEqual(by_key[("grafana", "A")], "10.0.0.9")

    def test_static_fingerprint_stable_and_sensitive(self):
        zones = {
            "apex": {"name": "dev-mxhash.com", "static_records": []},
            "k8s": {"name": "k8s.dev-mxhash.com", "static_records": []},
        }
        apex = [{"name": "helm", "type": "A", "rdata": "192.168.1.219"}]
        a = BIND.bind_static_fingerprint(zones, apex, "apex")
        b = BIND.bind_static_fingerprint(zones, list(apex), "apex")
        self.assertEqual(a, b)
        apex2 = apex + [{"name": "mailu", "type": "A", "rdata": "192.168.1.219"}]
        self.assertNotEqual(a, BIND.bind_static_fingerprint(zones, apex2, "apex"))

    def test_slurp_zone_text_decodes_matching_key(self):
        payload = base64.b64encode(b"zone body").decode("ascii")
        slurp = {
            "results": [
                {
                    "item": {"key": "k8s", "value": {"name": "k8s.example"}},
                    "content": payload,
                }
            ]
        }
        self.assertEqual(BIND.bind_slurp_zone_text(slurp, "k8s"), "zone body")
        self.assertEqual(BIND.bind_slurp_zone_text(slurp, "apex"), "")


if __name__ == "__main__":
    unittest.main()
