# SPDX-License-Identifier: MPL-2.0
"""PLAN-034c：数据库引擎与 Session。"""
from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL_ENV = "QYUNSLATION_DATABASE_URL"

_engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def get_database_url(override: str | None = None) -> str | None:
    if override is not None:
        return override.strip() or None
    return (os.environ.get(DATABASE_URL_ENV) or "").strip() or None


def init_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    """初始化全局引擎。url 缺省时读环境变量；仍空则抛错。"""
    global _engine, SessionLocal
    resolved = get_database_url(url)
    if not resolved:
        raise RuntimeError(
            f"{DATABASE_URL_ENV} is not set; refuse silent SQLite production fallback"
        )
    connect_args: dict[str, Any] = {}
    engine_kwargs: dict[str, Any] = {"echo": echo, "future": True}
    if resolved.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # :memory: 必须 StaticPool，否则每连接空库
        if ":memory:" in resolved:
            from sqlalchemy.pool import StaticPool

            engine_kwargs["poolclass"] = StaticPool
    engine_kwargs["connect_args"] = connect_args
    _engine = create_engine(resolved, **engine_kwargs)
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_engine() -> Engine | None:
    return _engine


def reset_engine() -> None:
    """测试用：释放全局引擎。"""
    global _engine, SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    SessionLocal = None


def get_session() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise RuntimeError("database engine not initialized")
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping_db(engine: Engine | None = None) -> bool:
    eng = engine if engine is not None else _engine
    if eng is None:
        return False
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
