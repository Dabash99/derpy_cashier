from __future__ import annotations

import pytest

from derby.core.db import addons_repo, categories_repo, products_repo
from derby.features.pos.addon_selection import validate_and_snapshot_addons
from derby.features.pos.exceptions import AddonSelectionError


def _product_with_group(db_conn, min_select=0, max_select=None):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2000)
    group_id = addons_repo.create_group(db_conn, "الحجم", min_select=min_select, max_select=max_select)
    addon_small = addons_repo.create_addon(db_conn, group_id, "صغير", 0)
    addon_large = addons_repo.create_addon(db_conn, group_id, "كبير", 500)
    addons_repo.set_product_addon_groups(db_conn, product_id, [group_id])
    return product_id, group_id, addon_small, addon_large


def test_no_groups_no_addons_is_fine(db_conn):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "شاي", "", 1000)
    snapshots = validate_and_snapshot_addons(db_conn, product_id, [])
    assert snapshots == []


def test_required_group_rejects_empty_selection(db_conn):
    product_id, _group_id, _small, _large = _product_with_group(db_conn, min_select=1, max_select=1)
    with pytest.raises(AddonSelectionError):
        validate_and_snapshot_addons(db_conn, product_id, [])


def test_valid_selection_within_min_max(db_conn):
    product_id, _group_id, addon_small, _large = _product_with_group(db_conn, min_select=1, max_select=1)
    snapshots = validate_and_snapshot_addons(db_conn, product_id, [addon_small])
    assert len(snapshots) == 1
    assert snapshots[0].addon_id == addon_small
    assert snapshots[0].price_delta_piasters == 0


def test_too_many_selections_rejected(db_conn):
    product_id, _group_id, addon_small, addon_large = _product_with_group(db_conn, min_select=0, max_select=1)
    with pytest.raises(AddonSelectionError):
        validate_and_snapshot_addons(db_conn, product_id, [addon_small, addon_large])


def test_unlimited_max_select(db_conn):
    product_id, _group_id, addon_small, addon_large = _product_with_group(db_conn, min_select=0, max_select=None)
    snapshots = validate_and_snapshot_addons(db_conn, product_id, [addon_small, addon_large])
    assert len(snapshots) == 2


def test_addon_from_unattached_group_rejected(db_conn):
    product_id, _group_id, _small, _large = _product_with_group(db_conn)
    other_group = addons_repo.create_group(db_conn, "إضافات أخرى")
    other_addon = addons_repo.create_addon(db_conn, other_group, "كريمة", 300)
    with pytest.raises(AddonSelectionError):
        validate_and_snapshot_addons(db_conn, product_id, [other_addon])


def test_inactive_addon_rejected(db_conn):
    product_id, _group_id, addon_small, _large = _product_with_group(db_conn)
    addons_repo.set_addon_active(db_conn, addon_small, False)
    with pytest.raises(AddonSelectionError):
        validate_and_snapshot_addons(db_conn, product_id, [addon_small])


def test_inactive_group_requirement_is_not_enforced(db_conn):
    product_id, group_id, _small, _large = _product_with_group(db_conn, min_select=1, max_select=1)
    addons_repo.set_group_active(db_conn, group_id, False)
    # The group is retired -- no longer required, and selecting nothing is fine.
    snapshots = validate_and_snapshot_addons(db_conn, product_id, [])
    assert snapshots == []
