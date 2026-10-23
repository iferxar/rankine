"""What this machine lets Rankine tune, and what is missing. Read-only; works with or without root.

Each feature is reported as {id, title, phase, state, detail, fix, command}:
state is "ready", "setup" (possible after the steps in fix/command), "unsupported" or "optional".
"""
from __future__ import annotations

import glob
import os
import shutil

from .. import __version__
from ..sensors.gpu import pci_name
from ..sensors.hwmon import read_int, read_text
from .gpu import drm_devices, parse_overdrive, parse_profiles

OVERDRIVE_BIT = 0x4000  # PP_OVERDRIVE_MASK in amdgpu's ppfeaturemask
OVERDRIVE_MASK = "amdgpu.ppfeaturemask=0xffffffff"
SMU_DIR = "/sys/kernel/ryzen_smu_drv"

# (family, first model, last model) -> codename, for the Ryzen desktop and mobile parts ryzen_smu knows.
_CODENAMES = [
    (0x17, 0x01, 0x01, "Summit Ridge"), (0x17, 0x08, 0x08, "Pinnacle Ridge"),
    (0x17, 0x11, 0x11, "Raven Ridge"), (0x17, 0x18, 0x18, "Picasso"),
    (0x17, 0x60, 0x60, "Renoir"), (0x17, 0x68, 0x68, "Lucienne"), (0x17, 0x71, 0x71, "Matisse"),
    (0x19, 0x20, 0x2F, "Vermeer"), (0x19, 0x40, 0x4F, "Rembrandt"), (0x19, 0x50, 0x5F, "Cezanne"),
    (0x19, 0x60, 0x6F, "Raphael"), (0x19, 0x70, 0x7F, "Phoenix"), (0x1A, 0x40, 0x4F, "Granite Ridge"),
]
# Curve Optimizer SMU commands are community-documented; only families verified on hardware are enabled.
_CURVE_OPTIMIZER_VERIFIED = {"Vermeer"}

_FAN_MODES = {0: "full speed", 1: "manual", 2: "firmware automatic"}


def _feature(id, title, phase, state, detail, fix="", command=""):
    return {"id": id, "title": title, "phase": phase, "state": state,
            "detail": detail, "fix": fix, "command": command}


def _watts(path: str) -> float | None:
    v = read_int(path)
    return v / 1e6 if v is not None else None


def _hex(path: str) -> int | None:
    text = read_text(path)
    try:
        return int(text, 0) if text else None
    except ValueError:
        return None


def bootloader() -> str | None:
    if os.path.exists("/etc/default/limine") or os.path.exists("/boot/limine.conf"):
        return "limine"
    if os.path.exists("/etc/sdboot-manage.conf"):
        return "systemd-boot"
    if os.path.exists("/boot/refind_linux.conf"):
        return "refind"
    if os.path.exists("/etc/default/grub"):
        return "grub"
    return None


def kernel_param_steps(param: str) -> tuple[str, str]:
    """(instructions, command) for adding a kernel parameter with the detected bootloader."""
    loader = bootloader()
    if loader == "grub":
        return (f"Add {param} to GRUB_CMDLINE_LINUX_DEFAULT in /etc/default/grub, regenerate the "
                "config and reboot.", "sudo grub-mkconfig -o /boot/grub/grub.cfg")
    if loader == "systemd-boot":
        return (f"Add {param} to LINUX_OPTIONS in /etc/sdboot-manage.conf, regenerate the entries "
                "and reboot.", "sudo sdboot-manage gen")
    if loader == "limine":
        return (f"Add {param} to KERNEL_CMDLINE[default] in /etc/default/limine, regenerate the "
                "entries and reboot.", "sudo limine-update")
    if loader == "refind":
        return f"Add {param} to the options in /boot/refind_linux.conf and reboot.", ""
    return f"Add {param} to the kernel command line in your bootloader and reboot.", ""


# ── GPU ──────────────────────────────────────────────────────────────────────

def _profiles(dev: str) -> tuple[list[str], str | None]:
    profiles, active = parse_profiles(read_text(f"{dev}/pp_power_profile_mode") or "")
    return [n for _, n in profiles], dict(profiles).get(active)


def _amdgpu_features(dev: str, hwmon: str | None) -> list[dict]:
    out = []

    cap = _watts(f"{hwmon}/power1_cap") if hwmon else None
    if cap is not None:
        lo, hi = _watts(f"{hwmon}/power1_cap_min"), _watts(f"{hwmon}/power1_cap_max")
        default = _watts(f"{hwmon}/power1_cap_default")
        detail = f"Set to {cap:.0f} W"
        if lo is not None and hi is not None:
            detail += f" · driver range {lo:.0f}–{hi:.0f} W"
        if default is not None:
            detail += f" · default {default:.0f} W"
        if hi is not None and default is not None and hi <= default:
            detail += ". The card only allows lowering it."
        out.append(_feature("gpu-power", "Power limit", "0.3", "ready", detail))
    else:
        out.append(_feature("gpu-power", "Power limit", "0.3", "unsupported",
                            "The driver does not expose power1_cap for this card."))

    level = read_text(f"{dev}/power_dpm_force_performance_level")
    names, active = _profiles(dev)
    if level is not None:
        detail = f"Performance level {level}"
        if active:
            detail += f" · profile {active.replace('_', ' ').title()}"
        if names:
            detail += f" · {len(names)} profiles"
        out.append(_feature("gpu-profile", "Performance profile", "0.3", "ready", detail))

    mode = read_int(f"{hwmon}/pwm1_enable") if hwmon else None
    if mode is not None:
        detail = f"Currently {_FAN_MODES.get(mode, f'mode {mode}')}"
        if os.path.exists(f"{dev}/gpu_od/fan_ctrl/fan_curve"):
            detail += " · firmware fan-curve table available"
        else:
            detail += " · Rankine would run the curve in software and hand back to firmware on exit"
        out.append(_feature("gpu-fan", "Fan curve", "0.3", "ready", detail))
    else:
        out.append(_feature("gpu-fan", "Fan curve", "0.3", "unsupported",
                            "The driver does not expose fan PWM control for this card."))

    text = read_text(f"{dev}/pp_od_clk_voltage")
    od = parse_overdrive(text) if text else None
    if od is not None:
        parts = []
        for key, name in (("sclk", "Core"), ("mclk", "memory")):
            if od.get(key) and key in od["range"]:
                lo, hi = od["range"][key]
                parts.append(f"{name} {od[key][-1]} MHz (driver range {lo}–{hi})")
        if "voltage_offset" in od:
            parts.append(f"voltage offset {od['voltage_offset']} mV")
        out.append(_feature("gpu-overdrive", "Clocks and undervolt", "0.4", "ready",
                            " · ".join(parts) or "Overdrive table present"))
    else:
        mask = _hex("/sys/module/amdgpu/parameters/ppfeaturemask")
        if mask is not None and not mask & OVERDRIVE_BIT:
            fix, command = kernel_param_steps(OVERDRIVE_MASK)
            out.append(_feature(
                "gpu-overdrive", "Clocks and undervolt", "0.4", "setup",
                f"Overdrive is off (ppfeaturemask {mask:#x}). While it is on, the kernel marks "
                "itself tainted; remove the parameter if you stop tuning.", fix, command))
        else:
            out.append(_feature("gpu-overdrive", "Clocks and undervolt", "0.4", "unsupported",
                                "This card exposes no overdrive table."))
    return out


def _gpus() -> list[dict]:
    gpus = []
    for card, dev, driver, hwmon in drm_devices():
        name = read_text(f"{dev}/product_name") or pci_name(dev) or driver
        if driver == "amdgpu":
            features = _amdgpu_features(dev, hwmon)
        elif driver == "nvidia":
            features = [_feature("gpu", "NVIDIA tuning", "", "unsupported",
                                 "Not planned until the AMD path is solid.")]
        else:
            features = [_feature("gpu", "GPU tuning", "", "unsupported",
                                 f"No tuning support for the {driver} driver.")]
        gpus.append({"name": name, "card": card, "driver": driver, "features": features})
    return gpus


# ── CPU ──────────────────────────────────────────────────────────────────────

def _cpuinfo() -> dict[str, str]:
    info = {}
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if not line.strip():
                    break  # first processor only
                key, _, value = line.partition(":")
                info[key.strip()] = value.strip()
    except OSError:
        pass
    return info


def codename(family: int, model: int) -> str | None:
    return next((n for f, lo, hi, n in _CODENAMES if f == family and lo <= model <= hi), None)


def _smu_module_installed() -> bool:
    release = os.uname().release
    return bool(glob.glob(f"/lib/modules/{release}/**/ryzen_smu.ko*", recursive=True))


def _cpu() -> dict:
    info = _cpuinfo()
    out = {"name": info.get("model name", "Unknown CPU"), "codename": None, "features": []}
    if info.get("vendor_id") != "AuthenticAMD":
        out["features"].append(_feature(
            "cpu", "CPU tuning", "", "unsupported",
            "Undervolting is locked on most recent Intel CPUs; only AMD Ryzen is planned."))
        return out

    family, model = int(info.get("cpu family", "0")), int(info.get("model", "0"))
    code = out["codename"] = codename(family, model)
    loaded = os.path.isdir(SMU_DIR)

    if loaded:
        version = read_text(f"{SMU_DIR}/drv_version")
        smu = _feature("cpu-smu", "SMU access", "0.5", "ready",
                       f"ryzen_smu {version} loaded" if version else "ryzen_smu loaded")
    elif _smu_module_installed():
        smu = _feature("cpu-smu", "SMU access", "0.5", "setup",
                       "The ryzen_smu module is installed but not loaded.",
                       "Load it now, and add ryzen_smu to /etc/modules-load.d/ to load it at boot.",
                       "sudo modprobe ryzen_smu")
    else:
        smu = _feature("cpu-smu", "SMU access", "0.5", "setup",
                       "Needs the ryzen_smu kernel module, which talks to the CPU's System "
                       "Management Unit.", "Install it from the AUR, then load it.",
                       "paru -S ryzen_smu-dkms-git && sudo modprobe ryzen_smu")
    out["features"].append(smu)

    pm_state = "ready" if loaded and os.path.exists(f"{SMU_DIR}/pm_table") else "setup"
    out["features"].append(_feature(
        "cpu-pmtable", "Per-core voltage and PBO limits", "0.5", pm_state,
        "Real per-core voltage and PPT/TDC/EDC usage from the SMU power table, replacing "
        "today's estimated Vcore." + ("" if loaded else " Needs SMU access.")))

    if code in _CURVE_OPTIMIZER_VERIFIED:
        out["features"].append(_feature(
            "cpu-curve", "Curve Optimizer and PBO", "0.5", "ready" if loaded else "setup",
            f"{code} is supported. Settings live in the SMU and reset on reboot."
            + ("" if loaded else " Needs SMU access.")))
    else:
        out["features"].append(_feature(
            "cpu-curve", "Curve Optimizer and PBO", "0.5", "unsupported",
            f"Not verified on {code or f'family {family:#x} model {model:#x}'} yet."))
    return out


# ── Stability tooling ────────────────────────────────────────────────────────

def _tools() -> list[dict]:
    out = []
    if shutil.which("stress-ng"):
        out.append(_feature("tool-stress", "Load generator", "0.6", "ready",
                            "stress-ng installed, for per-core stability runs."))
    else:
        out.append(_feature("tool-stress", "Load generator", "0.6", "setup",
                            "stress-ng drives the per-core stability runs.", "",
                            "sudo pacman -S stress-ng"))
    if shutil.which("rasdaemon") or shutil.which("ras-mc-ctl"):
        out.append(_feature("tool-ras", "Hardware error log", "0.6", "ready",
                            "rasdaemon installed: machine-check errors are recorded."))
    else:
        out.append(_feature("tool-ras", "Hardware error log", "0.6", "optional",
                            "Rankine reads machine-check errors from the kernel log; rasdaemon "
                            "keeps a longer, structured record.", "Available in the AUR.",
                            "paru -S rasdaemon && sudo systemctl enable --now rasdaemon"))
    if os.path.exists("/run/lactd.sock") or shutil.which("lact"):
        out.append(_feature("tool-lact", "LACT", "0.3", "ready",
                            "LACT is installed; Rankine may use its daemon for GPU settings."))
    else:
        out.append(_feature("tool-lact", "LACT", "0.3", "optional",
                            "Not installed. Rankine will write GPU settings itself."))
    return out


def probe() -> dict:
    return {"version": __version__, "privileged": os.geteuid() == 0,
            "gpus": _gpus(), "cpu": _cpu(), "tools": _tools()}
