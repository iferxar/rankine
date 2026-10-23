"""D-Bus names shared by rankine-tuned and the UI."""
import os

BUS_NAME = "io.github.iferxar.Rankine.Tuned"
OBJECT_PATH = "/io/github/iferxar/Rankine/Tuned"
INTERFACE = BUS_NAME
UNIT = "rankine-tuned.service"


def use_session_bus() -> bool:
    """Development mode: RANKINE_TUNED_BUS=session talks to an unprivileged helper on the session bus."""
    return os.environ.get("RANKINE_TUNED_BUS") == "session"
