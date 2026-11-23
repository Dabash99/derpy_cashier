from __future__ import annotations

from datetime import timedelta

from derby.core.db import ps_devices_repo, settings_repo, users_repo
from derby.core.utils.time_utils import utc_now
from derby.features.dashboard import alerts_service
from derby.features.playstation import ps_service


def test_a_clean_database_only_flags_drawer_and_backup(db_conn):
    # A brand-new database has never opened the drawer and never taken a
    # backup -- both of those alerts are correct here; everything else
    # (low stock, overdue customers, long PS sessions, ...) must be quiet.
    alerts = alerts_service.compute_alerts(db_conn)
    texts = [a.text for a in alerts]
    assert any("الدرج" in t for t in texts)
    assert any("النسخة الاحتياطية" in t for t in texts)
    assert len(alerts) == 2


def test_low_stock_alert_fires_when_enabled(db_conn):
    from derby.core.db import stock_items_repo

    stock_items_repo.create_stock_item(db_conn, "حليب", "l", min_qty=5)
    alerts = alerts_service.compute_alerts(db_conn)
    assert any("مخزون" in a.text for a in alerts)


def test_low_stock_alert_respects_its_toggle(db_conn):
    from derby.core.db import stock_items_repo

    stock_items_repo.create_stock_item(db_conn, "حليب", "l", min_qty=5)
    settings_repo.set_value(db_conn, "alert_low_stock_enabled", "0")
    alerts = alerts_service.compute_alerts(db_conn)
    assert not any("مخزون" in a.text for a in alerts)


def test_ps_long_session_alert(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 10000, 15000)
    now = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner_id, now=now - timedelta(hours=7))

    alerts = alerts_service.compute_alerts(db_conn, now=now)
    assert any("بلايستيشن" in a.text for a in alerts)


def test_drawer_not_opened_alert(db_conn):
    alerts = alerts_service.compute_alerts(db_conn)
    assert any("الدرج" in a.text for a in alerts)


def test_drawer_alert_clears_once_opened_today(db_conn):
    from derby.features.inventory import drawer_service

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    drawer_service.open_drawer(db_conn, 0, owner_id)
    alerts = alerts_service.compute_alerts(db_conn)
    assert not any("الدرج" in a.text for a in alerts)


def test_a_failing_check_never_crashes_compute_alerts(db_conn, monkeypatch):
    from derby.core.db import stock_items_repo

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(stock_items_repo, "list_low_stock", _boom)
    alerts = alerts_service.compute_alerts(db_conn)  # must not raise
    assert isinstance(alerts, list)


def test_only_owner_sees_alerts_center_on_dashboard(qapp, db_conn):
    from derby.features.dashboard.daily_stats_screen import DailyStatsScreen

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")

    owner_screen = DailyStatsScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    assert owner_screen._alerts_center is not None

    cashier_screen = DailyStatsScreen(db_conn, users_repo.get_user(db_conn, cashier_id))
    assert cashier_screen._alerts_center is None
