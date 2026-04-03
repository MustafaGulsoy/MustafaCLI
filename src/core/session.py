"""Session Persistence — save and restore conversation sessions.

Sessions are stored as JSON files in ~/.mustafacli/sessions/.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .context import ContextManager, Message, MessageRole


@dataclass
class Session:
    id: str
    created: datetime
    updated: datetime
    model: str
    working_dir: str
    messages: list[dict] = field(default_factory=list)
    summary: str = ""
    tokens_used: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created": self.created.isoformat(),
            "updated": self.updated.isoformat(),
            "model": self.model,
            "working_dir": self.working_dir,
            "messages": self.messages,
            "summary": self.summary,
            "tokens_used": self.tokens_used,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Session:
        return cls(
            id=data["id"],
            created=datetime.fromisoformat(data["created"]),
            updated=datetime.fromisoformat(data["updated"]),
            model=data.get("model", ""),
            working_dir=data.get("working_dir", "."),
            messages=data.get("messages", []),
            summary=data.get("summary", ""),
            tokens_used=data.get("tokens_used", 0),
        )

    @classmethod
    def from_context(cls, context: ContextManager, model: str, working_dir: str,
                     session_id: Optional[str] = None) -> Session:
        now = datetime.now()
        msg_dicts = []
        for msg in context.messages:
            d = msg.to_dict()
            d["timestamp"] = msg.timestamp.isoformat()
            msg_dicts.append(d)
        stats = context.get_stats()
        return cls(
            id=session_id or uuid.uuid4().hex[:12],
            created=now, updated=now, model=model,
            working_dir=working_dir, messages=msg_dicts,
            summary=getattr(context, '_compacted_summary', '') or '',
            tokens_used=stats.get("total_tokens", 0),
        )

    def restore_into(self, context: ContextManager) -> None:
        context.clear()
        if self.summary:
            context._compacted_summary = self.summary
        for md in self.messages:
            try:
                role = MessageRole(md["role"])
            except (ValueError, KeyError):
                continue
            ts = datetime.fromisoformat(md["timestamp"]) if "timestamp" in md else datetime.now()
            context.add_message(Message(
                role=role, content=md.get("content", ""), timestamp=ts,
                tool_calls=md.get("tool_calls"),
                tool_call_id=md.get("tool_call_id"),
                tool_name=md.get("name"),
            ))


class SessionManager:
    def __init__(self, sessions_dir: Optional[Path] = None) -> None:
        self._dir = sessions_dir or Path.home() / ".mustafacli" / "sessions"
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, session: Session) -> Path:
        session.updated = datetime.now()
        fp = self._dir / f"{session.id}.json"
        fp.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return fp

    def load(self, session_id: str) -> Session:
        fp = self._dir / f"{session_id}.json"
        return Session.from_dict(json.loads(fp.read_text(encoding="utf-8")))

    def list_sessions(self, limit: int = 10) -> list[Session]:
        sessions = []
        for p in self._dir.glob("*.json"):
            try:
                sessions.append(Session.from_dict(json.loads(p.read_text(encoding="utf-8"))))
            except Exception:
                continue
        sessions.sort(key=lambda s: s.updated, reverse=True)
        return sessions[:limit]

    def get_latest(self) -> Optional[Session]:
        s = self.list_sessions(limit=1)
        return s[0] if s else None
