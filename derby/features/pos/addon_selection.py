"""Validates a chosen set of addon_ids against a product's attached addon
groups (min/max select), and builds the name/price snapshot that gets
stored on the order line -- menu edits later must never change an order
that's already in the cart or paid.
"""
from __future__ import annotations

from typing import List

from derby.core.db import addons_repo
from derby.features.pos.exceptions import AddonSelectionError


class AddonSnapshot:
    def __init__(self, addon_id: int, name: str, price_delta_piasters: int) -> None:
        self.addon_id = addon_id
        self.name = name
        self.price_delta_piasters = price_delta_piasters


def validate_and_snapshot_addons(conn, product_id: int, addon_ids: List[int]) -> List[AddonSnapshot]:
    attached_group_ids = set(addons_repo.get_product_group_ids(conn, product_id))
    active_groups = {
        group["id"]: group
        for group in (addons_repo.get_group(conn, gid) for gid in attached_group_ids)
        if group is not None and group["is_active"]
    }

    selected_addons_by_group = {}
    snapshots = []
    for addon_id in addon_ids:
        addon = addons_repo.get_addon(conn, addon_id)
        if addon is None or not addon["is_active"] or addon["group_id"] not in active_groups:
            raise AddonSelectionError("addon {0} is not valid for this product".format(addon_id))
        selected_addons_by_group.setdefault(addon["group_id"], []).append(addon)
        snapshots.append(AddonSnapshot(addon["id"], addon["name"], addon["price_delta_piasters"]))

    for group_id, group in active_groups.items():
        count = len(selected_addons_by_group.get(group_id, []))
        if count < group["min_select"]:
            raise AddonSelectionError(
                "group {0!r} requires at least {1} selection(s), got {2}".format(
                    group["name"], group["min_select"], count
                )
            )
        if group["max_select"] is not None and count > group["max_select"]:
            raise AddonSelectionError(
                "group {0!r} allows at most {1} selection(s), got {2}".format(
                    group["name"], group["max_select"], count
                )
            )

    return snapshots
