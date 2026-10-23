# Tuning roadmap

Status: **phase 2 done**: GPU power limit, performance profile, fan curve, clocks and undervolt,
applied through `rankine-tuned` with polkit, automatic revert and GPU hang detection, plus a
boot profile for settings that passed a stability test. **Phase 3 done** for Zen 3: PBO limits and
per-core Curve Optimizer through `ryzen_smu`, with live SMU readings. The monitor itself still never
needs root.
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
  the driver accepts). Rankine also refuses positive voltage offsets: only undervolting is offered.
- Anything enabled by default. Every tuning feature is opt-in and the monitor keeps working
  without it.

## What the reference machine exposes

Measured on the development box (Ryzen 9 5900XT, Radeon RX 6900 XT, `0x73bf` rev `c0`, kernel 7.3 CachyOS):

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
  hardware maps to one polkit action (`io.github.iferxar.Rankine.Tuned.gpu-power`, `….gpu-profile`,
  `….gpu-fan`; later `….gpu-clocks`, `….cpu-curve`), so the user can allow some and not others, and admins can lock them down.
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
3. **Nothing at boot until proven.** Settings are applied at boot only after the user saves them as
   the boot profile, and settings that raise power or clocks, or undervolt, must first pass a
   stability test. If a session that had the profile applied does not end with a clean service
   stop (crash, freeze, reset button, power loss), or the GPU hangs, the profile is turned off and
   the user is told why.
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
- Development without root: `python -m rankine.tuned --session`, then run the UI with
  `RANKINE_TUNED_BUS=session`.

### Phase 1 · GPU basics (v0.3) — done
- **Power limit** slider within `power1_cap_min…max`.
- **Performance level** (auto, low, high) and **power profile** selector; the custom profile is left
  out until overdrive.
- **Fan curve** editor: up to 8 points, temperature never decreasing and speed never dropping as it
  rises. The helper runs the curve once a second on the edge temperature (RDNA2 has no firmware
  fan-curve table; that is RDNA3+), speeds up at once and slows down only after a 3 °C drop, goes to
  100 % if the hotspot reaches 100 °C, and hands the fan back to firmware (`pwm1_enable=2`) whenever
  it stops or loses the temperature reading.
- **Before/after view.** Averages of the 20 s before a change and the 20 s after it: power,
  temperature, hotspot, clock, fan and load.
- How the rules are implemented:
  - D-Bus methods `SetPowerLimit`, `SetPerformance`, `SetFanCurve` each check their polkit action
    (`auth_admin_keep` for the active session) with `pkcheck` against the caller's pid and start time.
  - Every change starts a 15 s countdown in the helper; `Confirm` (only from the same client) keeps
    it, `Revert` or the timeout restores the values from before the change. Several changes inside
    one countdown are kept or reverted together.
  - Before the first change to a card, its original values go to `/run/rankine-tuned/baseline.json`.
    Stopping the service restores them; `ExecStopPost=rankine-tuned --reset` restores them after a
    crash. `Reset` puts one card back from the UI ("Restore original settings").
  - Nothing is applied at boot yet, so rule 3 holds trivially: profiles that survive a reboot come
    after the stability checks of phase 2.
- Tests: `python -m unittest` runs the fan curve and control logic, plus the whole service on the
  session bus against a fake amdgpu sysfs tree (`tests/`).

### Phase 2 · GPU overdrive (v0.4) — done
Requires `amdgpu.ppfeaturemask=0xffffffff`. The UI explains how to add it for the user's bootloader
and that it should be removed if tuning is abandoned. With it, the driver also widens the power
limit (an RX 6900 XT goes from 237–264 W to 237–303 W); raising it above the default is flagged as
overclocking in the UI.
- `pp_od_clk_voltage` is parsed for the current values and the ranges the card accepts (`OD_RANGE`),
  so limits come from the driver, not from a table in Rankine. Example (RX 6900 XT):
  core 500–3000 MHz, memory 674–1075 MHz, plus `OD_VDDGFX_OFFSET`.
- `SetOverdrive` (polkit action `gpu-clocks`) edits the max core clock, max memory clock and voltage
  offset, then commits with `c`, as the driver expects. The driver gives no range for the voltage
  offset, so Rankine allows −150 to 0 mV.
- The values the service saw at startup, which is boot, are shown as defaults on each slider.
- **GPU hang detection:** the service reads `/dev/kmsg` (hence `CAP_SYSLOG` in the unit) for `amdgpu`
  ring timeouts and GPU resets. On one, it drops any unconfirmed change and puts every changed card
  back to its original clocks, voltage and power; the fan curve stays, since it only adds cooling.
- **Stability test:** the user runs their own load (a game or benchmark) and starts a 5, 15 or
  30 minute test. It fails on a GPU hang, is inconclusive if the GPU spent less than half the time
  above 80 % load, and passes otherwise.
- Tests simulate the overdrive table's edit-then-commit behaviour and feed fake kernel log lines
  through a pipe.

### Boot profile (v0.4) — done
- **Apply at boot** saves the card's current settings (power limit, level and profile, clocks,
  voltage offset, fan curve) to `/var/lib/rankine-tuned/profile.json` (`StateDirectory=`). Saving
  and turning it back on use the polkit action `boot-profile`; removing it needs no authorization.
- The UI only allows saving settings above the boot defaults, or undervolted, after they passed a
  stability test in the same session with exactly those values. Saving is refused while a change
  is waiting for confirmation.
- At startup, before anything is applied, the service records the boot values (still shown as the
  slider defaults and restored when it stops), then applies the profile.
- Guard, in `session.json`: each start records whether the profile was applied, and only a clean
  service stop marks the session clean. A session that applied the profile and ended any other way
  turns the profile off before the next boot can apply it. A GPU hang turns it off at once. Either
  way the Tuning page shows why and offers to turn it back on.
- Tests restart the service against the fake card: clean stop and start applies the profile, a
  killed process does not, a GPU hang turns it off, and removing it stops it from applying.

### Phase 3 · CPU, manual (v0.5) — done for Zen 3 desktop (Vermeer)
Requires the `ryzen_smu` kernel module (`ryzen_smu-dkms-git` in the AUR) loaded at boot. Its sysfs
files are root-only, so everything goes through `rankine-tuned` (`rankine/tuned/ryzen.py`).
- **PM table.** Layouts for tables `0x380804`/`0x380805` (16 cores) and `0x380904`/`0x380905`
  (8 cores) are known; limits and package values share positions, the per-core blocks move. The
  values pass a sanity check (plausible limits and voltages) before they are trusted. The Tuning
  page shows PPT/TDC/EDC usage against the limits and each core's voltage, effective clock (which
  averages in sleep time), power and share of time awake. Zen 3 firmware reports EDC pinned near
  its limit even at idle; the page says so. Feeding these real voltages into the dashboard's
  estimated Vcore is still to do.
- **PBO limits** (`SetCpuLimits`, polkit `cpu-limits`): RSMU `0x53`/`0x54`/`0x55` take mW and mA.
  Lowering is free; raising is capped at 1.5 times the limits read at startup, which come from the
  BIOS, and is flagged as needing a stability test.
- **Curve Optimizer** (`SetCurveOptimizer`, polkit `cpu-curve`): MP1 `0x35` per core, with the core
  mask `ccd << 28 | core << 20` and the margin in the low 16 bits; RSMU `0x7C` reads a core's margin
  back. ZenStates-Core marked that read as unsure, so `rankine-tuned --cpu-report --verify-co` writes
  −5 to the last core, reads it back and restores it. On a Ryzen 9 5900XT (table `0x380805`) it read
  back −5. If the read fails, Curve Optimizer stays off, since the BIOS margins could not be restored.
  Only −30 to 0 is offered; restores write whatever the BIOS had, positive margins included.
  Per-core margins need complete CCDs (the OS core order only matches the SMU's physical index then);
  otherwise one margin applies to all cores.
- Cores map to CCDs by shared L3 cache.
- The CPU joins the same machinery as the GPUs, as device `cpu`: confirmation countdown, original
  values restored on stop or crash (SMU settings are volatile, so a reboot also clears them), the
  boot profile, and hang detection, which now also reacts to machine-check errors
  (`mce: [Hardware Error]`).
- The stability test takes a target: for the CPU it counts time above 80 % CPU load. Curve
  Optimizer errors often show at light load or idle rather than under full load, which the page
  points out; phase 4's per-core search is what covers that properly.
- Tests use a fake SMU (`tests/fakesmu.py`) that encodes margins and limits the way the real one
  does, both directly and through the service on the session bus.

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
| 0.3 | GPU power limit, profiles, fan curve, before/after (done) | polkit approval |
| 0.4 | GPU clocks and undervolt, GPU stability check (done) | kernel parameter |
| 0.5 | CPU PM table readings, manual PBO / Curve Optimizer (done, Zen 3) | `ryzen_smu` from the AUR |
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
