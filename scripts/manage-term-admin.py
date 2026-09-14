#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Deployment-only grant/revoke flow for PLAN-060 term administrators.

This script deliberately has no HTTP route.  It is intended for an operator
with host access and a secret held outside the repository; user-facing Gradio
and OIDC APIs cannot call it or self-escalate a membership.
"""
from __future__ import annotations

import argparse
import getpass
import hmac
import os
import sys

from qyunslation.persist import repo
from qyunslation.persist.audit import record_audit
from qyunslation.persist import db

_TOKEN_ENV = "QYUNSLATION_TERM_ROLE_ADMIN_TOKEN"
_TENANT_ENV = "QYUNSLATION_WORKBENCH_TENANT"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="授予或撤销公司术语管理员权限。")
    parser.add_argument("--user-sub", required=True, help="已登录用户的稳定 subject")
    parser.add_argument("--tenant", default=os.environ.get(_TENANT_ENV), help="租户 slug")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--grant", action="store_true", help="授予 term_admin")
    actions.add_argument("--revoke", action="store_true", help="恢复普通 member")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    tenant_slug = (args.tenant or "").strip()
    expected = (os.environ.get(_TOKEN_ENV) or "").strip()
    if not tenant_slug or not expected:
        print(
            f"ERROR: require --tenant (or {_TENANT_ENV}) and protected {_TOKEN_ENV}",
            file=sys.stderr,
        )
        return 2
    supplied = getpass.getpass("Deployment authorization token: ")
    if not hmac.compare_digest(supplied, expected):
        print("ERROR: authorization failed", file=sys.stderr)
        return 3
    try:
        db.init_engine()
        if db.SessionLocal is None:
            raise RuntimeError("database session is unavailable")
        with db.SessionLocal.begin() as session:
            tenant = repo.get_or_create_tenant(session, slug=tenant_slug)
            membership = repo.ensure_membership(
                session, tenant_id=tenant.id, user_sub=args.user_sub
            )
            membership.role = "term_admin" if args.grant else "member"
            record_audit(
                session,
                actor_sub="deployment:term-role-admin",
                action="workbench.term_admin.grant" if args.grant else "workbench.term_admin.revoke",
                extra={"tenant": tenant.slug, "user_sub": args.user_sub, "role": membership.role},
            )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {args.user_sub} is now {'term_admin' if args.grant else 'member'} in {tenant_slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
