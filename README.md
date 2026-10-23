# Rankine

A glanceable hardware sensor monitor for Linux, built with Python, PySide6 and QML.

- **CPU**: temperature, total and per-thread load and clock, package power, core voltage, estimated current
- **GPU**: temperature and hotspot, load, clock, power, voltage, estimated current, VRAM (AMD via sysfs, NVIDIA via `nvidia-smi`, Intel partial)
- **Memory**: RAM and swap usage; module size, vendor, part number and XMP/JEDEC rating read from the SPD EEPROMs (DDR4 `ee1004`, DDR5 `spd5118`); configured speed and voltage; DIMM temperature when a sensor exists
- **Fans and drives**: every hwmon fan header that reports a speed, NVMe/SATA temperatures
- Min / avg / max per metric since launch (or since *Reset Stats*), 120-second history graphs

Sensors are discovered from `/sys/class/hwmon` by driver name, so nothing is hard-coded to one machine.

## Run

```sh
sudo pacman -S --needed pyside6      # Arch / CachyOS
python3 -m rankine                   # from the repository root
python3 -m rankine --demo            # simulated telemetry
python3 -m rankine --dump            # one JSON snapshot, no GUI
```

### App menu entry

```sh
scripts/install-user.sh
```

Installs `~/.local/bin/rankine`, a desktop entry and the icon for the current user, pointing at this checkout.

## Readings that need root

| Reading | Why | How to enable |
|---|---|---|
| CPU power and current | RAPL energy counters are root-only since Linux 5.10 ([CVE-2020-8694](https://nvd.nist.gov/vuln/detail/CVE-2020-8694)) | `scripts/enable-rapl.sh` installs a systemd-tmpfiles rule that makes them world-readable |
| Configured DIMM speed and voltage | SMBIOS tables are root-only; without them Rankine shows the module's rated XMP/JEDEC values, marked as such | Click **Detect** in the Memory card: it runs `dmidecode` once through polkit and caches the result in `~/.cache/rankine/dimm.json` (dropped automatically if the installed modules change) |

CPU voltage on boards whose Super I/O chip doesn't label its inputs (e.g. `nct6687`) is a best guess and marked *est.*; compare it with your BIOS.

## Tuning (preview)

Rankine is growing into a GPU and CPU tuner (power limit, fan curve, undervolt, Curve Optimizer).
The plan and the safety rules it follows are in [docs/TUNING.md](docs/TUNING.md).

The **Tuning** tab shows what this machine supports and what each feature still needs, such as a
kernel parameter or the `ryzen_smu` module. With the `rankine-tuned` service running, it also sets
the GPU power limit, performance profile, fan curve, clocks and undervolt (AMD), compares readings
before and after each change, and runs timed stability tests. Every change asks for your password
through polkit and reverts after 15 seconds unless you keep it. If the GPU hangs, or the service
stops, the card goes back to its original settings. Settings that passed a stability test can be
saved to apply at every boot; a crash or GPU hang turns that off until you turn it back on. On Ryzen 5000
desktop CPUs with the [`ryzen_smu`](https://github.com/amkillam/ryzen_smu) module loaded, it also
shows the SMU's per-core voltage and power and sets PBO limits and per-core Curve Optimizer. The service is optional and off by
default:

```sh
sudo systemctl enable --now rankine-tuned.service   # packaged install
sudo scripts/install-tuned.sh                       # from a checkout, then enable as above
```

Tests: `python -m unittest` (the service tests need a D-Bus session bus).

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
