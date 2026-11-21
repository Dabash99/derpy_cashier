"""Builds the data the Home screen's "الطلبات المفتوحة" section renders:
one lightweight query across every open order (derby/core/db/orders_repo.py
list_open_orders_with_summary), plus the live PlayStation provisional
price/elapsed time for any device that currently has a running session --
the same ps_service.current_state() call daily_stats_service.py already
makes per active device, so this stays bounded by the (small, fixed)
device count rather than by the number of open orders.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from derby.core.db import orders_repo, ps_devices_repo
from derby.core.i18n import ar
from derby.core.utils.time_utils import parse_utc_iso, utc_now
from derby.features.playstation import ps_service

KIND_TABLE = "table"
KIND_PLAYSTATION = "playstation"
KIND_TAKEAWAY = "takeaway"

# "configurable" per the spec, but with no settings-table change in scope
# for this read-only feature -- a code constant is the decision.
STALE_ORDER_THRESHOLD_SECONDS = 2 * 3600

_MODE_LABELS = {
    ps_service.MODE_SINGLE: ar.PS_MODE_SINGLE_LABEL,
    ps_service.MODE_MULTI: ar.PS_MODE_MULTI_LABEL,
}


@dataclass
class OpenOrderCard:
    order_id: int
    kind: str
    name: str
    opened_at_utc: datetime
    elapsed_seconds: int
    total_piasters: int
    item_count: int
    opened_by_name: Optional[str]
    is_estimated_total: bool
    ps_mode_label: Optional[str] = None


def _running_states_by_device(conn: sqlite3.Connection, now: datetime) -> dict:
    states = {}
    for device in ps_devices_repo.list_devices(conn, active_only=True):
        state = ps_service.current_state(conn, device["id"], now=now)
        if state["running_session"] is not None:
            states[device["id"]] = state
    return states


def list_open_order_cards(conn: sqlite3.Connection, now: Optional[datetime] = None) -> List[OpenOrderCard]:
    now = now if now is not None else utc_now()
    rows = orders_repo.list_open_orders_with_summary(conn)
    running_by_device = _running_states_by_device(conn, now)

    cards = []
    for row in rows:
        opened_at = parse_utc_iso(row["opened_at_utc"])
        default_elapsed = max(0, int((now - opened_at).total_seconds()))

        if row["device_id"] is not None:
            kind = KIND_PLAYSTATION
            name = row["device_name"] or ""
            running = running_by_device.get(row["device_id"])
            if running is not None:
                total_piasters = running["provisional_price_piasters"]
                is_estimated = True
                elapsed_seconds = running["elapsed_seconds"]
                mode_label = _MODE_LABELS.get(running["running_session"]["mode"])
            else:
                total_piasters = row["total_piasters"]
                is_estimated = False
                elapsed_seconds = default_elapsed
                mode_label = None
        elif row["table_id"] is not None:
            kind = KIND_TABLE
            name = row["table_name"] or ""
            total_piasters = row["total_piasters"]
            is_estimated = False
            elapsed_seconds = default_elapsed
            mode_label = None
        else:
            kind = KIND_TAKEAWAY
            name = row["label"] or ar.DASHBOARD_OPEN_ORDER_TAKEAWAY_LABEL
            total_piasters = row["total_piasters"]
            is_estimated = False
            elapsed_seconds = default_elapsed
            mode_label = None

        cards.append(
            OpenOrderCard(
                order_id=row["id"],
                kind=kind,
                name=name,
                opened_at_utc=opened_at,
                elapsed_seconds=elapsed_seconds,
                total_piasters=total_piasters,
                item_count=row["item_count"],
                opened_by_name=row["opened_by_name"],
                is_estimated_total=is_estimated,
                ps_mode_label=mode_label,
            )
        )

    # PlayStation first, then longest-open first (earliest opened_at_utc).
    cards.sort(key=lambda card: (0 if card.kind == KIND_PLAYSTATION else 1, card.opened_at_utc))
    return cards
