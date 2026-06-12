"""Persistent chat history for the Blender sidebar."""

from __future__ import annotations

import datetime as _dt
import json

import bpy

CHAT_HISTORY_TEXT_NAME = "Claude Chat History"
MAX_MESSAGES = 80
MAX_HISTORY_CHARS = 60_000
MAX_MESSAGE_CHARS = 12_000


def _now():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _text_block():
    text = bpy.data.texts.get(CHAT_HISTORY_TEXT_NAME)
    if text is None:
        text = bpy.data.texts.new(CHAT_HISTORY_TEXT_NAME)
    return text


def _short_text(value, max_chars=MAX_MESSAGE_CHARS):
    value = str(value or "").strip()
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}... [truncated]"


def _read_messages():
    text = bpy.data.texts.get(CHAT_HISTORY_TEXT_NAME)
    if text is None:
        return []
    messages = []
    for line in text.as_string().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("role"):
            messages.append(item)
    return messages


def _write_messages(messages):
    messages = list(messages)[-MAX_MESSAGES:]
    while len(messages) > 1:
        body = "\n".join(json.dumps(item, sort_keys=True) for item in messages)
        if len(body) <= MAX_HISTORY_CHARS:
            break
        messages = messages[1:]
    text = _text_block()
    text.clear()
    if messages:
        text.write("\n".join(json.dumps(item, sort_keys=True) for item in messages))
    return text


def _set_state(scene):
    state = getattr(scene, "claude_blender", None)
    if not state:
        return
    messages = _read_messages()
    state.chat_history_text_name = CHAT_HISTORY_TEXT_NAME
    state.chat_history_turn_count = len(messages)
    state.chat_history_status = f"{len(messages)} message(s) in chat"


def append_message(scene, *, role, content, title="", context_summary="", effective_prompt=""):
    messages = _read_messages()
    messages.append(
        {
            "timestamp": _now(),
            "role": str(role or "system"),
            "title": _short_text(title, 300),
            "content": _short_text(content),
            "context_summary": _short_text(context_summary, 600),
            "effective_prompt": _short_text(effective_prompt, 2400),
        }
    )
    _write_messages(messages)
    if scene:
        _set_state(scene)
    return messages[-1]


def recent_messages(limit=8):
    limit = max(1, int(limit or 8))
    return _read_messages()[-limit:]


def all_messages():
    return _read_messages()


def clear_history(scene=None):
    text = _text_block()
    text.clear()
    if scene:
        _set_state(scene)
        state = getattr(scene, "claude_blender", None)
        if state:
            state.chat_history_status = "Chat cleared"
    return {"ok": True, "message": "Chat history cleared", "text_datablock": CHAT_HISTORY_TEXT_NAME}


def chat_text():
    messages = _read_messages()
    parts = []
    for item in messages:
        role = str(item.get("role") or "system").title()
        timestamp = item.get("timestamp") or ""
        content = item.get("content") or ""
        parts.append(f"[{timestamp}] {role}\n{content}")
    return "\n\n".join(parts)


def register():
    pass


def unregister():
    pass
