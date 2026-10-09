"""
Engine and session setup.

SQLite: every transaction starts with BEGIN IMMEDIATE, which takes the database
write lock up front, so check-then-act sequences inside one unit of work cannot
interleave. PostgreSQL: units of work lock the intent row with SELECT ... FOR UPDATE.
The serialization ablation (ProtocolConfig.serialize_intent=False) does not change
this; it splits the decision and the attempt reservation into two transactions.
"""

from __future__ import annotations

import threading

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from intentguard.models import Base


def make_engine(url: str, *, durable: bool = True) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True)

    in_memory = ":memory:" in url or url in ("sqlite://", "sqlite:///")
    shared_memory = "mode=memory" in url
    kwargs: dict = {}
    if in_memory:
        kwargs["poolclass"] = StaticPool
    elif shared_memory:
        # SQLAlchemy would pick a per-thread pool for memory URIs, which closes
        # connections still in use once more than five threads have connected.
        kwargs.update(poolclass=QueuePool, pool_size=8, max_overflow=16)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 60}, **kwargs)

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        dbapi_conn.isolation_level = None  # SQLAlchemy emits BEGIN itself (see below)
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=60000")
        if not (in_memory or shared_memory):
            cur.execute("PRAGMA journal_mode=WAL")
        if not durable:
            cur.execute("PRAGMA synchronous=OFF")
        cur.close()

    # Shared-cache in-memory databases (used by the benchmark for speed) report lock
    # conflicts immediately instead of honouring busy_timeout, so transactions on
    # them are serialized with a process-local lock instead. Separate transactions
    # can still interleave, which is what the serialization ablation needs.
    txn_lock = threading.RLock() if shared_memory else None

    @event.listens_for(engine, "begin")
    def _on_begin(conn):  # type: ignore[no-untyped-def]
        if txn_lock is not None:
            txn_lock.acquire()
            conn.info["ig_txn_lock"] = True
        try:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
        except BaseException:
            if txn_lock is not None and conn.info.pop("ig_txn_lock", False):
                txn_lock.release()
            raise

    if txn_lock is not None:
        # Released on check-in, i.e. after COMMIT/ROLLBACK has actually executed
        # (the Connection "commit" event fires before the COMMIT statement).
        @event.listens_for(engine, "checkin")
        def _on_checkin(_dbapi_conn, record):  # type: ignore[no-untyped-def]
            if record.info.pop("ig_txn_lock", False):
                txn_lock.release()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)
