"""Compose stack catalog helpers (infra_compose_stacks).

Phase 2: gate evaluation, dedicated-unit selection, image lists, topo-sort.
"""

from __future__ import annotations

from typing import Any


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _all_true(flag_names: list[str] | None, variables: dict[str, Any]) -> bool:
    if not flag_names:
        return True
    for name in flag_names:
        if not _as_bool(variables.get(name, False)):
            return False
    return True


def compose_stack_enabled(stack: dict[str, Any], variables: dict[str, Any]) -> bool:
    enable = (stack.get("enable_when") or {}).get("all_true") or []
    return _all_true(enable, variables)


def compose_stack_skip_dedicated(stack: dict[str, Any], variables: dict[str, Any]) -> bool:
    skip = (stack.get("skip_dedicated_unit_when") or {}).get("all_true") or []
    if not skip:
        return False
    return _all_true(skip, variables)


def compose_stacks_for_render(
    stacks: list[dict[str, Any]],
    variables: dict[str, Any],
) -> list[dict[str, Any]]:
    """Stacks whose enable_when gates are open (including shared nginx sidecars)."""
    return [s for s in stacks or [] if compose_stack_enabled(s, variables)]


def compose_stacks_for_units(
    stacks: list[dict[str, Any]],
    variables: dict[str, Any],
) -> list[dict[str, Any]]:
    """Stacks that get a dedicated systemd unit / compose project."""
    return [
        s
        for s in stacks or []
        if compose_stack_enabled(s, variables) and not compose_stack_skip_dedicated(s, variables)
    ]


def compose_stacks_in_group(
    stacks: list[dict[str, Any]],
    variables: dict[str, Any],
    start_group: str,
) -> list[dict[str, Any]]:
    group = (start_group or "").strip()
    return [s for s in compose_stacks_for_units(stacks, variables) if s.get("start_group") == group]


def compose_topo_sort(stacks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Topological sort by after[] among the provided stacks (stable on catalog order)."""
    stacks = list(stacks or [])
    if not stacks:
        return []
    ids = {s["id"] for s in stacks}
    by_id = {s["id"]: s for s in stacks}
    order_index = {s["id"]: i for i, s in enumerate(stacks)}
    indeg = {s["id"]: 0 for s in stacks}
    children: dict[str, list[str]] = {s["id"]: [] for s in stacks}
    for s in stacks:
        for dep in s.get("after") or []:
            if dep not in ids:
                continue
            children[dep].append(s["id"])
            indeg[s["id"]] += 1
    ready = sorted([i for i, d in indeg.items() if d == 0], key=lambda x: order_index[x])
    out: list[dict[str, Any]] = []
    while ready:
        node = ready.pop(0)
        out.append(by_id[node])
        for child in children[node]:
            indeg[child] -= 1
            if indeg[child] == 0:
                ready.append(child)
                ready.sort(key=lambda x: order_index[x])
    if len(out) != len(stacks):
        raise ValueError("compose stack after[] contains a cycle among enabled stacks")
    return out


def compose_stacks_to_projects(
    stacks: list[dict[str, Any]],
    variables: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve dedicated systemd projects from the catalog (catalog order)."""
    catalog = list(stacks or [])
    by_id = {s["id"]: s for s in catalog}
    projects: list[dict[str, Any]] = []
    for s in compose_stacks_for_units(catalog, variables):
        after_units: list[str] = []
        for dep_id in s.get("after") or []:
            dep = by_id.get(dep_id)
            if dep is None:
                continue
            if not compose_stack_enabled(dep, variables):
                continue
            if compose_stack_skip_dedicated(dep, variables):
                continue
            unit = variables.get(dep["unit_name_var"])
            if unit:
                after_units.append(f"{unit}.service")
        unit_name = variables.get(s["unit_name_var"])
        project_dir = variables.get(s["project_dir_var"])
        if not unit_name or not project_dir:
            continue
        projects.append(
            {
                "id": s["id"],
                "unit_name": unit_name,
                "project_dir": project_dir,
                "description": s.get("description") or s["id"],
                "up_extra": s.get("up_extra") or "",
                "after_units": " ".join(after_units),
            }
        )
    return projects


def compose_stacks_to_images(
    stacks: list[dict[str, Any]],
    variables: dict[str, Any],
) -> list[str]:
    """Unique image refs for dedicated (non-shared) enabled stacks, catalog order."""
    images: list[str] = []
    seen: set[str] = set()
    for s in compose_stacks_for_units(stacks, variables):
        image = variables.get(s["image_var"])
        if not image or image in seen:
            continue
        seen.add(image)
        images.append(image)
    return images


class FilterModule(object):
    def filters(self):
        return {
            "compose_stack_enabled": compose_stack_enabled,
            "compose_stack_skip_dedicated": compose_stack_skip_dedicated,
            "compose_stacks_for_render": compose_stacks_for_render,
            "compose_stacks_for_units": compose_stacks_for_units,
            "compose_stacks_in_group": compose_stacks_in_group,
            "compose_topo_sort": compose_topo_sort,
            "compose_stacks_to_projects": compose_stacks_to_projects,
            "compose_stacks_to_images": compose_stacks_to_images,
        }
