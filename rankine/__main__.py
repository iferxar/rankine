import argparse
import json
import sys
import time

from . import __version__


def main() -> int:
    parser = argparse.ArgumentParser(prog="rankine", description="Hardware sensor monitor for Linux.")
    parser.add_argument("--demo", action="store_true", help="simulated telemetry instead of real sensors")
    parser.add_argument("--dump", action="store_true", help="print one sensor snapshot as JSON and exit")
    parser.add_argument("--interval", type=float, default=1.0, help="refresh interval in seconds")
    parser.add_argument("--version", action="version", version=f"rankine {__version__}")
    args = parser.parse_args()

    from .sensors import DemoMonitor, Monitor
    monitor = DemoMonitor() if args.demo else Monitor()

    if args.dump:
        monitor.sample()
        time.sleep(1)  # load and power need two readings
        snap = monitor.sample()
        snap.pop("history")
        json.dump(snap, sys.stdout, indent=2, default=str)
        print()
        return 0

    from .app import run
    return run(monitor, args.interval)


if __name__ == "__main__":
    sys.exit(main())
