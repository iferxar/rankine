# Tuning roadmap

Status: **phase 0 done** (helper service and read-only Tuning page); nothing changes hardware yet.
Rankine still only reads sensors, and the monitor never needs root.
This document describes how it could grow into a tuner for the GPU (in the spirit of MSI Afterburner)
and the CPU (in the spirit of ClockTuner for Ryzen), and the rules it has to follow while doing so.

## Goals

- Adjust GPU power limit, clocks, voltage offset and fan curve, and see the effect live in the
  dashboard next to the numbers being changed.
- Adjust AMD Ryzen per-core Curve Optimizer offsets and PBO limits, first by hand, later with an
  automatic per-core search.
- Help the user prove a setting is stable before it becomes permanent.

## Non-goals

- Memory timing or BIOS-level overclocking. Those belong in firmware setup.
- Bypassing vendor limits (raising power caps beyond `power1_cap_max`, unlocking voltage above what
  the driver accepts).
- Anything enabled by default. Every tuning feature is opt-in and the monitor keeps working
  without it.

## What the reference machine exposes

Measured on the development box (Ryzen 9 5900XT, Radeon RX 6800 XT class `0x73bf`, kernel 7.3 CachyOS):

| Interface | State | Notes |
|---|---|---|
| `hwmon/power1_cap` | writable by root | range 237–264 W, default 264 W, so only lowering is possible |
| `hwmon/pwm1_enable`, `pwm1` | writable by root | `2` = firmware auto (zero-RPM at idle); `1` = manual |
| `power_dpm_force_performance_level`, `pp_power_profile_mode` | writable by root | force clocks / pick a workload profile |
| `pp_od_clk_voltage` | **absent** | overdrive is off: `amdgpu.ppfeaturemask=0xfff7bfff` lacks bit `0x4000` |
| `ryzen_smu` driver | not installed | needed for Curve Optimizer and PBO; available as a DKMS package in the AUR |
| `rasdaemon`, `stress-ng` | not installed | useful for error reporting and load generation |

Consequence: the GPU power limit and fan curve can be built today; GPU clocks and undervolting need
the user to add `amdgpu.ppfeaturemask=0xffffffff` to the kernel command line; CPU tuning needs
`ryzen_smu`.

## Architecture

```
 rankine (UI, user)  ──D-Bus──▶  rankine-tuned (system service, root)
        │                               │
   reads sysfs                    writes sysfs / SMU
   (as today)                     validates every request
                                  owns the revert watchdog
```

- **Privileged helper `rankine-tuned`.** A small Python system service activated over the system
  D-Bus (`io.github.iferxar.Rankine.Tuned`). The UI never runs as root. Each method that changes
  hardware maps to one polkit action (`io.github.iferxar.Rankine.Tuned.gpu-power`, `….gpu-clocks`,
  `….gpu-fan`, `….cpu-curve`), so the user can allow some and not others, and admins can lock them down.
- **Allowlist, not passthrough.** The helper accepts typed requests ("set power cap to 245 W on
  card1"), checks them against the ranges the driver itself advertises, and writes the files. It
  never takes a path or a raw string from the UI.
- **Capability probe.** The helper reports what each device supports and, when something is missing,
  why ("overdrive disabled by ppfeaturemask", "ryzen_smu not loaded"). The UI shows that as guidance
  instead of hiding controls silently.
- **Reuse before writing.** LACT already ships a GPU daemon with an API. Before writing the GPU half
  of the helper, evaluate talking to `lactd` when it is installed and only fall back to our own
  writes when it is not (see open questions).

## Safety rules

These apply to every phase and are not optional:

1. **Apply, then confirm.** Every change starts a countdown (default 15 s). If the UI does not confirm
   (because the screen froze or the user is not sure), the helper restores the previous values. Same
   idea as changing display resolution.
2. **The helper owns the revert,** not the UI. If the UI crashes or the session dies, the watchdog
   still fires. On helper shutdown, everything returns to firmware defaults (fan back to `pwm1_enable=2`).
3. **Nothing at boot until proven.** Settings are applied at boot only after the user marks a
   profile stable. A boot counter records whether the last boot reached "profile applied and
   confirmed"; if it did not, the next boot skips the profile and tells the user.
4. **Undo is always one click** ("Reset to defaults"), and a CLI escape hatch exists for a broken
   graphical session: `rankine-tuned --reset`.
5. **Log every write** to the journal with old and new values.
6. **Clear disclaimer** at first use: tuning can cause crashes and data corruption and may affect
   warranty; the software comes with no warranty (GPL-3.0, sections 15–16).

## Phases

### Phase 0 · Groundwork (v0.2) — done
- `rankine-tuned` (`rankine/tuned/`): system D-Bus service with `Version()` and `Probe()`, systemd
  unit (`data/systemd/`), bus policy (`data/dbus/`), capability probe (`rankine/tuned/probe.py`).
- Read-only **Tuning** page listing what is available and what is missing, with the exact steps to
  enable it (kernel parameter for the detected bootloader, AUR package). When the helper is not
  running, the UI runs the same probe in-process, so the page works either way.
- Packaging: the helper ships in the same package but stays disabled until the user enables the unit.
  From a checkout, `sudo scripts/install-tuned.sh` copies the code to a root-owned directory first.
- The polkit policy is deferred to phase 1, together with the first method that needs it.
- Development without root: `python -m rankine.tuned --session`, then run the UI with
  `RANKINE_TUNED_BUS=session`.

### Phase 1 · GPU basics (v0.3)
- **Power limit** slider within `power1_cap_min…max`.
- **Performance level / power profile** selector.
- **Fan curve** editor: temperature → PWM points, with hysteresis and a minimum step interval so the
  fan does not hunt. The helper runs the curve (RDNA2 has no firmware fan-curve table; that is RDNA3+)
  and falls back to `pwm1_enable=2` whenever it stops.
- **Before/after view.** Capture N seconds of history under the old setting and N under the new one,
  and show average power, temperature, clock and fan side by side. The history buffers the dashboard
  already keeps are the starting point.

### Phase 2 · GPU overdrive (v0.4)
Requires `amdgpu.ppfeaturemask=0xffffffff`. The UI explains how to add it for the user's bootloader
and that it should be removed if tuning is abandoned.
- Parse `pp_od_clk_voltage`: it lists the ranges the card accepts (`OD_RANGE`), so limits come from the
  driver, not from a table in Rankine.
- Core clock min/max, memory clock max, voltage offset (undervolt) when the card exposes it. The
  write sequence is the driver's own: set values, then `c` to commit; `r` restores defaults.
- **Stability check:** run a GPU load the user chooses (any Vulkan benchmark) while Rankine watches
  the kernel log for `amdgpu` ring timeouts and GPU resets. A reset means the step failed.

### Phase 3 · CPU, manual (v0.5)
Requires the `ryzen_smu` kernel module (Zen 3 "Vermeer" is supported by it).
- **Read the PM table first.** Even before any tuning, it gives real per-core voltage, PPT/TDC/EDC
  usage and limits. That replaces today's estimated Vcore in the dashboard, which is worth shipping on
  its own.
- PBO limits (PPT, TDC, EDC) and per-core Curve Optimizer offsets set by hand.
- SMU settings are volatile and reset on reboot, which makes experimenting safer than BIOS changes;
  the "nothing at boot until proven" rule still applies when re-applying them.
- The exact SMU mailbox commands for Curve Optimizer on Vermeer are community-documented, not
  vendor-documented. They must be verified on hardware and gated per CPU family.

### Phase 4 · CPU auto-tuner (experimental, v0.6+)
A per-core search in the spirit of CTR / PBO2 Tuner:
1. For each core, start at offset 0 and step negative (e.g. −5 at a time, then −1 near the edge).
2. At each step, pin a load to that core with `taskset`, alternating heavy, light and idle-transition
   phases. Curve Optimizer failures often show at low load or when a core wakes up, not only at full
   load.
3. Failure signals: machine-check errors in the kernel log (`mce: [Hardware Error]`, or rasdaemon when
   installed), computation errors from a self-verifying workload (`stress-ng --verify`, Prime95
   torture test), the process crashing, or the machine rebooting.
4. **Crash journal.** Before each step, the helper writes the core and offset to disk. After an
   unexpected reboot it reads the journal, marks that step failed, backs that core off and resumes.
5. Keep a safety margin: the final offset is the last stable one plus a couple of counts.
6. Present the result as a profile the user still has to mark stable after a long mixed-use run.

Expect a full run to take hours; it must be pausable and resumable.

## Milestones

| Version | Delivers | Needs from the user |
|---|---|---|
| 0.2 | helper + read-only Tuning page | enable the service |
| 0.3 | GPU power limit, profiles, fan curve, before/after | polkit approval |
| 0.4 | GPU clocks and undervolt, GPU stability check | kernel parameter |
| 0.5 | CPU PM table readings, manual PBO / Curve Optimizer | `ryzen_smu` from the AUR |
| 0.6+ | CPU auto-tuner (experimental) | time, and tolerance for test reboots |

## Open questions

- **LACT integration vs our own GPU writes.** Talking to `lactd` avoids duplicating a well-tested
  daemon; writing our own keeps Rankine self-contained. Possibly both, preferring LACT when present.
- **NVIDIA.** `nvidia-smi -pl` covers power limits; clock offsets depend on driver version and
  NVML support. Out of scope until the AMD path is solid.
- **Intel CPUs.** Undervolting is locked on most recent Intel parts; likely out of scope.
- **Helper language.** Python keeps one codebase; a compiled helper would be a smaller root surface.
  Start in Python, keep the helper small, and revisit.
- **Stress workloads.** Ship our own simple ones, or depend on `stress-ng` / Prime95 as optional
  dependencies?
