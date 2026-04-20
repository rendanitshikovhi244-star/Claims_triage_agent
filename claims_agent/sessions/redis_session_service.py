"""
redis_session_service.py
------------------------
A Redis-backed ADK session service.

Session STATE is persisted to Redis so it survives process restarts and is
shared across workers.  Events are kept in memory only — ADK event objects
contain non-serialisable internals, but agents read upstream results from
session state (via output_key / {placeholder} in instructions), not from
the event history, so this is fine for the claims pipeline.

Redis key schema:
  adk:state:<app_name>:<user_id>:<session_id>  →  JSON dict of state
  adk:sessions:<app_name>:<user_id>            →  Redis Set of session_ids
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Optional

import redis.asyncio as aioredis
from google.adk.events import Event
from google.adk.sessions import Session
from google.adk.sessions.base_session_service import (
    BaseSessionService,
    GetSessionConfig,
    ListSessionsResponse,
)

logger = logging.getLogger("claims_agent.sessions")

# Matches google.adk.sessions.state.State.TEMP_PREFIX
_TEMP_PREFIX = "temp:"


class RedisSessionService(BaseSessionService):
    """
    ADK session service backed by Redis.

    Args:
        redis_url: Redis connection URL (e.g. "redis://localhost:6379/0").
        ttl: Time-to-live in seconds for each session's state key. Default 24 h.
    """

    def __init__(self, redis_url: str, ttl: int = 86_400) -> None:
        self._redis_url = redis_url
        self._ttl = ttl
        # In-process store for Session objects (events live here only).
        # Keyed by "<app_name>:<user_id>:<session_id>".
        self._sessions: dict[str, Session] = {}

    # ------------------------------------------------------------------
    # Redis key helpers
    # ------------------------------------------------------------------

    def _state_key(self, app_name: str, user_id: str, session_id: str) -> str:
        return f"adk:state:{app_name}:{user_id}:{session_id}"

    def _index_key(self, app_name: str, user_id: str) -> str:
        return f"adk:sessions:{app_name}:{user_id}"

    def _mem_key(self, app_name: str, user_id: str, session_id: str) -> str:
        return f"{app_name}:{user_id}:{session_id}"

    def _get_redis(self) -> aioredis.Redis:
        return aioredis.from_url(self._redis_url, decode_responses=True)

    # ------------------------------------------------------------------
    # BaseSessionService interface
    # ------------------------------------------------------------------

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        session_id = session_id or uuid.uuid4().hex

        # If a prior state already exists in Redis for this id, merge it in
        # (supports resumable pipelines).
        r = self._get_redis()
        try:
            raw = await r.get(self._state_key(app_name, user_id, session_id))
            await r.sadd(self._index_key(app_name, user_id), session_id)
        finally:
            await r.aclose()

        merged: dict[str, Any] = {}
        if raw:
            merged.update(json.loads(raw))
        if state:
            merged.update(state)

        session = Session(
            id=session_id,
            app_name=app_name,
            user_id=user_id,
            state=merged,
            last_update_time=time.time(),
        )
        self._sessions[self._mem_key(app_name, user_id, session_id)] = session
        logger.debug("Session created  session=%s", session_id)
        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        mem_key = self._mem_key(app_name, user_id, session_id)
        session = self._sessions.get(mem_key)

        r = self._get_redis()
        try:
            raw = await r.get(self._state_key(app_name, user_id, session_id))
        finally:
            await r.aclose()

        if session is None:
            if raw is None:
                return None
            # Reconstruct a bare session from persisted state (no events)
            session = Session(
                id=session_id,
                app_name=app_name,
                user_id=user_id,
                state=json.loads(raw),
                last_update_time=time.time(),
            )
            self._sessions[mem_key] = session
        elif raw:
            # Sync any keys written by another worker / process
            session.state.update(json.loads(raw))

        return session

    async def list_sessions(
        self,
        *,
        app_name: str,
        user_id: Optional[str] = None,
    ) -> ListSessionsResponse:
        sessions = [
            s
            for s in self._sessions.values()
            if s.app_name == app_name
            and (user_id is None or s.user_id == user_id)
        ]
        return ListSessionsResponse(sessions=sessions)

    async def delete_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> None:
        self._sessions.pop(self._mem_key(app_name, user_id, session_id), None)
        r = self._get_redis()
        try:
            await r.delete(self._state_key(app_name, user_id, session_id))
            await r.srem(self._index_key(app_name, user_id), session_id)
        finally:
            await r.aclose()
        logger.debug("Session deleted  session=%s", session_id)

    # ------------------------------------------------------------------
    # Event persistence — flush state to Redis after every event
    # ------------------------------------------------------------------

    async def append_event(self, session: Session, event: Event) -> Event:
        # Delegate temp-state and state_delta handling to the base class
        event = await super().append_event(session, event)

        if not event.partial:
            # Persist only non-ephemeral state keys
            persistent = {
                k: v
                for k, v in session.state.items()
                if not k.startswith(_TEMP_PREFIX)
            }
            r = self._get_redis()
            try:
                await r.set(
                    self._state_key(session.app_name, session.user_id, session.id),
                    json.dumps(persistent),
                    ex=self._ttl,
                )
            finally:
                await r.aclose()
            logger.debug(
                "State flushed to Redis  session=%s  keys=%s",
                session.id,
                list(persistent.keys()),
            )

        return event
