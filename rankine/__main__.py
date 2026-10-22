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
    parser.add_argument("--import-dimm", action="store_true",
                        help="read `dmidecode -t 17` output from stdin and remember the configured "
                             "DIMM speed/voltage (e.g. sudo dmidecode -t 17 | rankine --import-dimm)")
    parser.add_argument("--version", action="version", version=f"rankine {__version__}")
    args = parser.parse_args()

    if args.import_dimm:
        from .sensors.spd import read_modules
        from .sensors.system import DMI_CACHE, parse_dmidecode, save_dimm_cache
        text = sys.stdin.read()
        if not save_dimm_cache(text, read_modules()):
            print("No configured memory speed or voltage found in the input.", file=sys.stderr)
            return 1
        info = parse_dmidecode(text)
        print(f"Saved {info.get('clock')} MT/s, {info.get('voltage')} V to {DMI_CACHE}")
        return 0

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
