"""language-lock: your agent answers in your language, and stays there.

Models drift: a long conversation in English turns into Chinese after a tool result in Chinese
(hermes-agent#130117), or a Spanish chat gets English replies after a few code turns. Language Lock
learns your language from your own recent messages (or a language you set). After each reply it
checks the reply's language without a model call. When the reply drifted, the agent is told at the
start of the next turn to switch back, and the drift is counted.

Asking for another language on purpose ("translate this to French", "answer in English") is
respected for that turn.

  /lang               your language, the last reply's language, drifts caught and fixed
  /lang set <code>    always expect this language (en, es, zh, hi, ...)
  /lang auto          learn it from your messages again
"""

from __future__ import annotations

import re
import threading
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from . import detect as D

if TYPE_CHECKING:
    from hermes_cli.plugins import PluginContext

_CTX: Any = None
_LOCK = threading.Lock()

# "translate to French", "answer in English", "en español", "auf Deutsch", "用中文"...
_ON_PURPOSE = re.compile(
    r"\btranslat\w*\b|\b(?:in|into|to)\s+(?:english|spanish|french|german|portuguese|italian|dutch|"
    r"indonesian|turkish|chinese|mandarin|japanese|korean|russian|ukrainian|arabic|persian|hindi|thai|"
    r"greek|hebrew)\b|\ben\s+(?:español|inglés|francés|français|anglais)\b|\bauf\s+(?:deutsch|englisch)\b|"
    r"用(?:中文|英文|日语)|英語で|日本語で|영어로|по-английски|по-русски", re.I)


@dataclass
class Session:
    heard: deque = field(default_factory=lambda: deque(maxlen=5))
    fixed: Optional[str] = None
    on_purpose: bool = False
    last_reply: Optional[str] = None
    drifted_to: Optional[str] = None
    drifts: int = 0
    corrected: int = 0
    stayed: int = 0


_SESSIONS: dict[str, Session] = {}


def _setting(name: str, default: Any) -> Any:
    try:
        value = _CTX.get_config(name, default) if _CTX is not None else default
    except Exception:
        value = default
    return default if value is None or value == "" else value


def _text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        return " ".join(p.get("text", "") for p in message if isinstance(p, dict) and p.get("type") == "text")
    return ""


def code_for(value: str) -> Optional[str]:
    value = (value or "").strip().lower()
    if value in D.NAMES:
        return value
    for code, label in D.NAMES.items():
        if label.lower() == value:
            return code
    return None


def _session(sid: str) -> Session:
    s = _SESSIONS.get(sid)
    if s is None:
        s = _SESSIONS[sid] = Session()
        while len(_SESSIONS) > 500:
            _SESSIONS.pop(next(iter(_SESSIONS)))
    return s


def expected(s: Session) -> Optional[str]:
    if s.fixed:
        return s.fixed
    configured = code_for(str(_setting("language", "")))
    if configured:
        return configured
    if not s.heard:
        return None
    (lang, n), = Counter(s.heard).most_common(1)
    # The latest message wins a tie, so a user who switches language is followed.
    return s.heard[-1] if n * 2 <= len(s.heard) else lang


# hooks ------------------------------------------------------------------

def on_pre_llm_call(session_id: str = "", user_message: Any = None, **_: Any) -> Optional[dict]:
    text = _text(user_message).strip()
    if text.startswith("/"):
        return None
    lang = D.detect(text)                  # outside the lock, so other sessions never wait on it
    with _LOCK:
        s = _session(session_id or "")
        if lang:
            s.heard.append(lang)
        s.on_purpose = bool(_ON_PURPOSE.search(text))
        want = expected(s)
        if not want or s.on_purpose:
            s.drifted_to = None
            return None
        if s.drifted_to and s.drifted_to != want:
            drifted, s.drifted_to = s.drifted_to, None
            s.corrected += 1
            return {"context": (
                f"[Language Lock] Your last reply was in {D.name(drifted)}, but the user writes in "
                f"{D.name(want)}. Reply in {D.name(want)} from now on. Keep code, commands, file names "
                "and quoted text exactly as they are.")}
        if str(_setting("remind", "drift")).lower() == "always":
            return {"context": f"[Language Lock] Reply in {D.name(want)}, the user's language."}
    return None


def on_post_llm_call(session_id: str = "", assistant_response: Any = None, **_: Any) -> None:
    reply = D.detect(_text(assistant_response), min_letters=20)
    with _LOCK:
        s = _session(session_id or "")
        s.last_reply = reply or s.last_reply
        want = expected(s)
        if not reply or not want or s.on_purpose:
            return None
        if reply != want:
            s.drifts += 1
            s.drifted_to = reply
        else:
            s.stayed += 1
    return None


# command ----------------------------------------------------------------

def lang_command(raw_args: str = "", session_id: str = "", **_: Any) -> str:
    words = (raw_args or "").split()
    with _LOCK:
        s = _session(session_id or "")
        if words[:1] == ["set"] and len(words) == 2:
            code = code_for(words[1])
            if not code:
                return "Unknown language. Use a code or name: " + ", ".join(sorted(D.NAMES))
            s.fixed = code
            return f"Language Lock expects {D.name(code)} in this session. /lang auto to learn it again."
        if words[:1] == ["auto"]:
            s.fixed = None
            return "Language Lock is learning your language from your messages again."
        if words:
            return "Usage: /lang [set <code> | auto]"
        want = expected(s)
        how = "set by you" if s.fixed else ("from settings" if code_for(str(_setting("language", ""))) else "from your messages")
        return "\n".join([
            f"Language Lock: your language is {D.name(want)} ({how})." if want else
            "Language Lock: not sure of your language yet; it learns from your next messages.",
            f"Last reply: {D.name(s.last_reply)}.",
            f"Replies in your language: {s.stayed}. Drifts caught: {s.drifts}. Corrections sent: {s.corrected}.",
        ])


def register(ctx: "PluginContext") -> None:
    global _CTX
    _CTX = ctx
    with _LOCK:
        _SESSIONS.clear()
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("post_llm_call", on_post_llm_call)
    ctx.register_command("lang", lang_command, description="Keep the agent replying in your language",
                         args_hint="[set <code> | auto]")
