"""A sanity check that opening the menu screen with ~100 products stays
fast -- uses synthetic data (not the owner's real photos) so this test
has no dependency on anything outside the repo.
"""
from __future__ import annotations

import time

from derby.core.db import categories_repo, products_repo, users_repo
from derby.features.menu.menu_screen import MenuScreen

PRODUCT_COUNT = 106


def test_menu_screen_opens_quickly_with_106_products(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1234")
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    for i in range(PRODUCT_COUNT):
        products_repo.create_product(db_conn, category_id, "منتج {0}".format(i), "Product {0}".format(i), 1000 + i)

    started = time.perf_counter()
    screen = MenuScreen(db_conn, owner_id)
    screen.resize(1200, 700)
    screen.show()
    qapp.processEvents()
    elapsed = time.perf_counter() - started

    print("time to build+show MenuScreen with {0} products: {1:.3f}s".format(PRODUCT_COUNT, elapsed))
    assert elapsed < 3
    assert len(screen._products_table._products) == PRODUCT_COUNT
