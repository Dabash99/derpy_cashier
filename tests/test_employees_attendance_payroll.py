from __future__ import annotations

from datetime import date, timedelta

from derby.core.db import users_repo
from derby.core.utils.time_utils import utc_now
from derby.features.employees import attendance_service, employee_service, payroll_service


def _owner(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, owner_id)


def test_create_employee_is_audited(db_conn):
    owner = _owner(db_conn)
    employee = employee_service.create_employee(db_conn, "أحمد", "0100000000", "كاشير", "monthly", 500000, owner)
    assert employee["name"] == "أحمد"
    row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'employee_created'").fetchone()
    assert row is not None


def test_clock_in_then_out_computes_hours(db_conn):
    owner = _owner(db_conn)
    employee = employee_service.create_employee(db_conn, "أحمد", None, None, "monthly", 500000, owner)

    attendance_service.clock_in(db_conn, employee["id"], owner)
    row = db_conn.execute("SELECT * FROM attendance WHERE employee_id = ?", (employee["id"],)).fetchone()
    # back-date the clock-in by 2 hours so hours_for_period has something to measure
    db_conn.execute(
        "UPDATE attendance SET clock_in_utc = ? WHERE id = ?",
        ((utc_now() - timedelta(hours=2)).isoformat(), row["id"]),
    )
    attendance_service.clock_out(db_conn, employee["id"], owner)

    today = date.today()
    hours = attendance_service.hours_for_period(db_conn, employee["id"], today.replace(day=1).isoformat(), today.isoformat())
    assert hours >= 1.9


def test_payroll_sheet_math_and_payment_creates_expense_and_marks_lines_applied(db_conn):
    owner = _owner(db_conn)
    employee = employee_service.create_employee(db_conn, "أحمد", None, None, "monthly", 500000, owner)
    today = date.today()

    payroll_service.add_bonus(db_conn, employee["id"], 10000, today, "مكافأة", owner)
    payroll_service.add_advance(db_conn, employee["id"], 20000, today, "سلفة", owner)
    payroll_service.add_deduction(db_conn, employee["id"], 5000, today, "جزاء", owner)

    line = payroll_service.build_sheet_line(db_conn, employee, today.year, today.month)
    assert line.base_piasters == 500000
    assert line.bonuses_piasters == 10000
    assert line.advances_piasters == 20000
    assert line.deductions_piasters == 5000
    assert line.net_piasters == 500000 + 10000 - 20000 - 5000

    before_expense_count = db_conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    payment = payroll_service.record_payment(db_conn, line, today.year, today.month, "cash", owner)
    after_expense_count = db_conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    assert after_expense_count == before_expense_count + 1
    assert payment["net_piasters"] == line.net_piasters

    # Lines already applied must not be double-counted in a rebuilt sheet.
    line2 = payroll_service.build_sheet_line(db_conn, employee, today.year, today.month)
    assert line2.bonuses_piasters == 0
    assert line2.advances_piasters == 0
    assert line2.deductions_piasters == 0

    audit_row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'payroll_paid'").fetchone()
    assert audit_row is not None


def test_instapay_payroll_payment_does_not_affect_drawer_expected_cash(db_conn):
    from derby.features.inventory import drawer_service

    owner = _owner(db_conn)
    employee = employee_service.create_employee(db_conn, "أحمد", None, None, "monthly", 500000, owner)
    drawer_service.open_drawer(db_conn, 0, owner["id"])
    before = drawer_service.expected_cash_piasters(db_conn)

    today = date.today()
    line = payroll_service.build_sheet_line(db_conn, employee, today.year, today.month)
    payroll_service.record_payment(db_conn, line, today.year, today.month, "instapay", owner)

    after = drawer_service.expected_cash_piasters(db_conn)
    assert after == before  # cash drawer must be unaffected by a non-cash payroll payment
