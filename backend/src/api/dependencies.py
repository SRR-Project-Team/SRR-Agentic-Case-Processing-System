#!/usr/bin/env python3
"""Shared dependency helpers for route modules."""

from __future__ import annotations

from typing import Dict


def user_role(current_user: Dict) -> str:
    return (current_user or {}).get("role", "user")
