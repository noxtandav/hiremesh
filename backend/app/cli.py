"""Hiremesh admin CLI.

Usage (inside the running api container, or any env with the backend deps
installed and DATABASE_URL set):

    python -m app.cli admin create --email me@example.com --name "Admin"
    python -m app.cli admin set-password --email me@example.com
    python -m app.cli admin list

The first form is the only way to create the very first admin in a fresh
deployment — there is no bootstrap-from-env path. After that you can use
the in-app /users API.

Passing --password on the command line works but lands in shell history;
omit it and you'll get an interactive prompt with echo off.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from typing import Literal

from sqlalchemy import select

from app.core import db as db_module
from app.core.security import hash_password
from app.models.user import User

MIN_PASSWORD_LEN = 12


def _read_password(provided: str | None) -> str:
    if provided is not None:
        if len(provided) < MIN_PASSWORD_LEN:
            sys.exit(
                f"Password must be at least {MIN_PASSWORD_LEN} characters."
            )
        return provided
    p1 = getpass.getpass("Password: ")
    p2 = getpass.getpass("Confirm:  ")
    if p1 != p2:
        sys.exit("Passwords don't match.")
    if len(p1) < MIN_PASSWORD_LEN:
        sys.exit(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
    return p1


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def cmd_create(args: argparse.Namespace) -> None:
    email = _normalize_email(args.email)
    role: Literal["admin", "recruiter"] = args.role
    pw = _read_password(args.password)

    with db_module.SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == email))
        if existing is not None:
            sys.exit(
                f"User {email} already exists. "
                f"Use `set-password` to reset their password."
            )
        user = User(
            email=email,
            name=args.name,
            password_hash=hash_password(pw),
            role=role,
            must_change_password=False,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Created {role}: {user.email} (id={user.id})")


def cmd_set_password(args: argparse.Namespace) -> None:
    email = _normalize_email(args.email)
    pw = _read_password(args.password)

    with db_module.SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            sys.exit(f"No user with email {email}.")
        user.password_hash = hash_password(pw)
        user.must_change_password = False
        if not user.is_active:
            print(
                f"Note: user {email} was inactive; reactivating.",
                file=sys.stderr,
            )
            user.is_active = True
        db.commit()
        print(f"Updated password for {user.email} (id={user.id}).")


def cmd_list(_args: argparse.Namespace) -> None:
    with db_module.SessionLocal() as db:
        users = db.scalars(
            select(User)
            .where(User.role == "admin")
            .order_by(User.created_at.asc())
        ).all()
        if not users:
            print("(no admins exist — run `admin create`)")
            return
        for u in users:
            status = "active" if u.is_active else "inactive"
            print(f"  {u.id:>3}  {u.email:<32}  {u.name:<24}  {status}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Hiremesh admin CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    admin = sub.add_parser("admin", help="Manage admin users")
    actions = admin.add_subparsers(dest="action", required=True)

    p_create = actions.add_parser("create", help="Create a new user")
    p_create.add_argument("--email", required=True)
    p_create.add_argument("--name", default="Admin")
    p_create.add_argument(
        "--role",
        default="admin",
        choices=["admin", "recruiter"],
        help="Defaults to admin.",
    )
    p_create.add_argument(
        "--password",
        help=(
            "Skip interactive prompt. Lands in shell history — prefer the "
            "prompt unless you're scripting."
        ),
    )
    p_create.set_defaults(func=cmd_create)

    p_setpw = actions.add_parser(
        "set-password", help="Reset a user's password"
    )
    p_setpw.add_argument("--email", required=True)
    p_setpw.add_argument("--password")
    p_setpw.set_defaults(func=cmd_set_password)

    p_list = actions.add_parser("list", help="List active admins")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
