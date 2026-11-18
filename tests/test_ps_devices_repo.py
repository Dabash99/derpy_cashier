from __future__ import annotations

from derby.core.db import ps_devices_repo


def test_migration_seeds_two_devices_with_zero_rates(db_conn):
    devices = ps_devices_repo.list_devices(db_conn)
    assert len(devices) == 2
    assert all(d["single_rate_piasters_per_hour"] == 0 and d["multi_rate_piasters_per_hour"] == 0 for d in devices)


def test_create_rename_set_rates_and_move(db_conn):
    device_id = ps_devices_repo.create_device(db_conn, "بلاي ستيشن 3")
    ps_devices_repo.rename_device(db_conn, device_id, "بلاي جديد")
    ps_devices_repo.set_rates(db_conn, device_id, 4000, 6000)
    device = ps_devices_repo.get_device(db_conn, device_id)
    assert device["name"] == "بلاي جديد"
    assert device["single_rate_piasters_per_hour"] == 4000
    assert device["multi_rate_piasters_per_hour"] == 6000


def test_set_active_and_list_active_only(db_conn):
    devices = ps_devices_repo.list_devices(db_conn)
    ps_devices_repo.set_active(db_conn, devices[0]["id"], False)
    active = ps_devices_repo.list_devices(db_conn, active_only=True)
    assert devices[0]["id"] not in [d["id"] for d in active]


def test_move_device_swaps_sort_order(db_conn):
    devices = ps_devices_repo.list_devices(db_conn)
    first_id, second_id = devices[0]["id"], devices[1]["id"]
    ps_devices_repo.move_device(db_conn, first_id, 1)
    reordered = ps_devices_repo.list_devices(db_conn)
    assert reordered[0]["id"] == second_id
    assert reordered[1]["id"] == first_id
