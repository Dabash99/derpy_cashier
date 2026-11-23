"""Employee record management (owner only)."""
from __future__ import annotations

import sqlite3
from typing import Optional

from derby.core import audit_service
from derby.core.db import employees_repo
from derby.features.employees.exceptions import NameRequiredError


def create_employee(
    conn: sqlite3.Connection,
    name: str,
    phone: Optional[str],
    job_title: Optional[str],
    pay_type: str,
    base_amount_piasters: int,
    requesting_user: sqlite3.Row,
    linked_user_id: Optional[int] = None,
) -> sqlite3.Row:
    name = (name or "").strip()
    if not name:
        raise NameRequiredError("name is required")
    employee_id = employees_repo.create_employee(conn, name, phone, job_title, pay_type, base_amount_piasters, linked_user_id)
    audit_service.log(
        conn, "employee_created", user=requesting_user, entity_type="employee", entity_id=employee_id,
        summary_ar="إضافة موظف: {0}".format(name),
        details={"name": name, "pay_type": pay_type, "base_amount_piasters": base_amount_piasters},
    )
    return employees_repo.get_employee(conn, employee_id)


def update_employee(
    conn: sqlite3.Connection,
    employee_id: int,
    name: str,
    phone: Optional[str],
    job_title: Optional[str],
    pay_type: str,
    base_amount_piasters: int,
    requesting_user: sqlite3.Row,
    linked_user_id: Optional[int] = None,
) -> sqlite3.Row:
    name = (name or "").strip()
    if not name:
        raise NameRequiredError("name is required")
    before = employees_repo.get_employee(conn, employee_id)
    employees_repo.update_employee(conn, employee_id, name, phone, job_title, pay_type, base_amount_piasters, linked_user_id)
    audit_service.log(
        conn, "employee_updated", user=requesting_user, entity_type="employee", entity_id=employee_id,
        summary_ar="تعديل بيانات موظف: {0}".format(name),
        details={
            "before": {"name": before["name"], "base_amount_piasters": before["base_amount_piasters"]},
            "after": {"name": name, "base_amount_piasters": base_amount_piasters},
        },
    )
    return employees_repo.get_employee(conn, employee_id)


def set_active(conn: sqlite3.Connection, employee_id: int, is_active: bool, requesting_user: sqlite3.Row) -> None:
    employee = employees_repo.get_employee(conn, employee_id)
    employees_repo.set_active(conn, employee_id, is_active)
    audit_service.log(
        conn, "employee_deactivated" if not is_active else "employee_updated", user=requesting_user,
        entity_type="employee", entity_id=employee_id,
        summary_ar="{0} موظف: {1}".format("تعطيل" if not is_active else "تفعيل", employee["name"]),
        severity=audit_service.SEVERITY_WARNING if not is_active else audit_service.SEVERITY_INFO,
    )
