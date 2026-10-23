"""Settings the user proved stable, applied when the service starts at boot.

Guard: the service records whether the profile was applied in this session and whether the session
ended cleanly. If the previous session had the profile applied and did not end cleanly (crash, hard
hang, reset button, power loss), the profile is turned off before it is applied again, and the user
is told why. A GPU hang in the kernel log turns it off too.
"""
from __future__ import annotations

import json
import os
import time

SYSTEM_STATE_DIR = "/var/lib/rankine-tuned"
PROFILE_FILE = "profile.json"
SESSION_FILE = "session.json"


def _read(path: str) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def boot_id() -> str:
    try:
        with open("/proc/sys/kernel/random/boot_id") as f:
            return f.read().strip()
    except OSError:
        return ""


class BootProfile:
    def __init__(self, state_dir: str):
        os.makedirs(state_dir, exist_ok=True)
        self.profile_path = os.path.join(state_dir, PROFILE_FILE)
        self.session_path = os.path.join(state_dir, SESSION_FILE)
        # {"enabled": bool, "notice": str, "saved": epoch, "cards": {card: CardState json}}
        self.data = _read(self.profile_path) or {"enabled": False, "notice": "", "cards": {}}

    @property
    def cards(self) -> dict:
        return self.data.get("cards", {})

    @property
    def enabled(self) -> bool:
        return bool(self.data.get("enabled")) and bool(self.cards)

    def _save(self) -> None:
        if self.cards:
            _write(self.profile_path, self.data)
        elif os.path.exists(self.profile_path):
            os.remove(self.profile_path)

    def store(self, card: str, state_json: dict) -> None:
        self.data.setdefault("cards", {})[card] = state_json
        self.data.update(enabled=True, notice="", saved=time.time())
        self._save()

    def remove(self, card: str) -> None:
        self.cards.pop(card, None)
        if not self.cards:
            self.data.update(enabled=False, notice="")
        self._save()

    def enable(self) -> None:
        self.data.update(enabled=True, notice="")
        self._save()

    def disable(self, notice: str) -> None:
        self.data.update(enabled=False, notice=notice)
        self._save()

    # ── session guard ──
    def start_session(self) -> None:
        """Turns the profile off if the last session that applied it did not end cleanly."""
        previous = _read(self.session_path)
        if previous and previous.get("applied") and not previous.get("clean") and self.enabled:
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(previous.get("applied_at", 0)))
            self.disable(f"Not applied: the session that applied it at {when} ended without a clean "
                         "shutdown (crash, freeze, reset or power loss). Re-enable it once you are "
                         "sure the settings were not the cause.")
        _write(self.session_path, {"boot_id": boot_id(), "applied": False, "clean": False})

    def mark_applied(self) -> None:
        _write(self.session_path, {"boot_id": boot_id(), "applied": True, "clean": False,
                                   "applied_at": time.time()})

    def end_session(self) -> None:
        session = _read(self.session_path) or {}
        session["clean"] = True
        _write(self.session_path, session)

    def to_json(self) -> dict:
        return {"enabled": self.enabled, "notice": self.data.get("notice", ""),
                "saved": self.data.get("saved"), "cards": self.cards}
