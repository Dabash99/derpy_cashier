from __future__ import annotations

from derby.core.db import discount_presets_repo, users_repo
from derby.features.pos.discount_math import DISCOUNT_KIND_PERCENT
from derby.features.pos.discount_presets_panel import DiscountPresetsPanel


def test_add_preset_through_the_panel_is_audited(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    panel = DiscountPresetsPanel(db_conn, owner)

    panel._name_input.setText("خصم العيد")
    panel._kind_input.setCurrentIndex(panel._kind_input.findData(DISCOUNT_KIND_PERCENT))
    panel._amount_input.setValue(10)
    panel._on_add()

    presets = discount_presets_repo.list_presets(db_conn)
    assert len(presets) == 1
    assert presets[0]["name"] == "خصم العيد"
    assert presets[0]["amount"] == 10

    row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'discount_preset_changed'").fetchone()
    assert row is not None


def test_preset_appears_as_a_quick_button_in_the_discount_dialog(qapp, db_conn):
    from derby.core.db import categories_repo, products_repo, tables_repo
    from derby.features.pos import orders_service
    from derby.features.pos.discount_dialog import DiscountDialog

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    discount_presets_repo.create_preset(db_conn, "خصم ثابت", DISCOUNT_KIND_PERCENT, 15)

    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner["id"])

    dialog = DiscountDialog(db_conn, order["id"], owner)
    dialog._on_use_preset(discount_presets_repo.list_presets(db_conn)[0])
    assert dialog._amount_input.text() == "15"
    dialog._on_apply()

    updated = db_conn.execute("SELECT * FROM orders WHERE id = ?", (order["id"],)).fetchone()
    assert updated["discount_piasters"] == 375  # 15% of 2500

    row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'discount_preset_used'").fetchone()
    assert row is not None
    assert "خصم ثابت" in row["details_json"]


def test_only_owner_manages_discount_presets():
    from derby.core.db.users_repo import ROLE_CASHIER, ROLE_OWNER
    from derby.features.auth import permissions

    assert permissions.manage_discount_presets(ROLE_OWNER) is True
    assert permissions.manage_discount_presets(ROLE_CASHIER) is False
