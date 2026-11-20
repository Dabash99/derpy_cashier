"""Holds who is currently logged in, for the lifetime of the app window."""
from __future__ import annotations

import sqlite3
from typing import Optional


class Session:
    def __init__(self) -> None:
        self.user: Optional[sqlite3.Row] = None

    def log_in(self, user: sqlite3.Row) -> None:
        self.user = user

    def log_out(self) -> None:
        self.user = None

    @property
    def is_logged_in(self) -> bool:
        return self.user is not None

    @property
    def role(self) -> str:
        if self.user is None:
            raise RuntimeError("no user logged in")
        return self.user["role"]
