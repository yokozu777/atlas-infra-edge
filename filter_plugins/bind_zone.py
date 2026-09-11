"""BIND zone helpers: parse dumped .db records, merge with static, fingerprint.

Dynamic RFC2136 updates live in .jnl. Rewriting .db without merging those
records (or deleting journals) drops kubelb / external-dns names.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _norm_name(name: str, origin: str = "") -> str:
    name = (name or "").rstrip(".")
    origin = (origin or "").rstrip(".")
    if not name or name == "@":
        return ""
    if origin and (name == origin or name.endswith("." + origin)):
        trimmed = name[: -len(origin)].rstrip(".")
        return trimmed
    return name


def _norm_record(rec: dict[str, Any], origin: str = "") -> dict[str, str]:
    rtype = str(rec.get("type") or "A").upper()
    rdata = str(rec.get("rdata") or "").strip()
    if rtype == "NS" and rdata and not rdata.endswith("."):
        rdata = rdata + "."
    return {
        "name": _norm_name(str(rec.get("name") or ""), origin),
        "type": rtype,
        "rdata": rdata,
    }


def bind_parse_zone_records(text: str, origin: str = "") -> list[dict[str, str]]:
    """Parse A/NS owner records from a BIND zone file (post-freeze dump)."""
    records: list[dict[str, str]] = []
    if not text:
        return records
    in_soa = False
    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line or line.startswith("$"):
            continue
        if in_soa:
            if ")" in line:
                in_soa = False
            continue
        tokens = line.split()
        if "SOA" in tokens:
            if "(" in line and ")" not in line:
                in_soa = True
            continue
        # Owner-less apex NS: "IN NS ns.example."
        if tokens[0] in ("IN",) and len(tokens) >= 2 and tokens[1] == "NS":
            continue
        if len(tokens) < 4:
            continue
        # name [ttl] IN A|NS rdata
        name = tokens[0]
        idx = 1
        if tokens[idx].isdigit():
            idx += 1
        if idx + 2 >= len(tokens) or tokens[idx] != "IN":
            continue
        rtype = tokens[idx + 1].upper()
        if rtype not in ("A", "NS"):
            continue
        rdata = tokens[idx + 2]
        rec = _norm_record({"name": name, "type": rtype, "rdata": rdata}, origin)
        if rec["name"]:
            records.append(rec)
    return records


def bind_union_zone_records(
    static_records: list[dict[str, Any]] | None,
    zone_text: str = "",
    origin: str = "",
) -> list[dict[str, str]]:
    """Static records win on (name, type); keep other A/NS from an existing .db."""
    static = [_norm_record(r, origin) for r in (static_records or [])]
    static = [r for r in static if r["name"]]
    keys = {(r["name"], r["type"]) for r in static}
    preserved = [
        r
        for r in bind_parse_zone_records(zone_text or "", origin)
        if (r["name"], r["type"]) not in keys
    ]
    return static + preserved


def bind_static_fingerprint(
    bind_zones: dict[str, Any] | None,
    apex_records: list[dict[str, Any]] | None = None,
    apex_zone_id: str = "apex",
) -> str:
    """Stable hash of templated static records (not journaled RFC2136 names)."""
    snapshot: dict[str, list[dict[str, str]]] = {}
    for zid, zone in sorted((bind_zones or {}).items()):
        origin = str((zone or {}).get("name") or "")
        if zid == apex_zone_id:
            raw = apex_records or []
        else:
            raw = (zone or {}).get("static_records") or []
        snapshot[zid] = sorted(
            [_norm_record(r, origin) for r in raw if _norm_record(r, origin)["name"]],
            key=lambda r: (r["name"], r["type"], r["rdata"]),
        )
    blob = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def bind_slurp_zone_text(slurp_result: dict[str, Any] | None, zone_key: str) -> str:
    """Decode ansible.builtin.slurp loop result for one bind_zones key."""
    import base64

    if not slurp_result:
        return ""
    for item in slurp_result.get("results") or []:
        loop_item = item.get("item") or {}
        if loop_item.get("key") != zone_key:
            continue
        if item.get("failed") or not item.get("content"):
            return ""
        try:
            return base64.b64decode(item["content"]).decode("utf-8")
        except (ValueError, TypeError, UnicodeDecodeError):
            return ""
    return ""


class FilterModule(object):
    def filters(self):
        return {
            "bind_parse_zone_records": bind_parse_zone_records,
            "bind_union_zone_records": bind_union_zone_records,
            "bind_static_fingerprint": bind_static_fingerprint,
            "bind_slurp_zone_text": bind_slurp_zone_text,
        }
