"""A fake amdgpu sysfs tree, so tuning code can be exercised without root or real hardware."""
import os

PROFILES = """PROFILE_INDEX(NAME) CLOCK_TYPE(NAME) FPS MinFreqType
 0 BOOTUP_DEFAULT*:
                    0(       GFXCLK)       0       5
 1 3D_FULL_SCREEN :
                    0(       GFXCLK)       0       5
 2   POWER_SAVING :
                    0(       GFXCLK)       0       5
 6         CUSTOM :
"""


def make(root: str) -> tuple[str, str]:
    """Creates device and hwmon directories under root; returns (dev, hwmon)."""
    dev = os.path.join(root, "device")
    hwmon = os.path.join(dev, "hwmon", "hwmon9")
    os.makedirs(hwmon)
    files = {
        f"{dev}/power_dpm_force_performance_level": "auto",
        f"{dev}/pp_power_profile_mode": PROFILES,
        f"{hwmon}/power1_cap": "264000000", f"{hwmon}/power1_cap_min": "237000000",
        f"{hwmon}/power1_cap_max": "264000000", f"{hwmon}/power1_cap_default": "264000000",
        f"{hwmon}/pwm1_enable": "2", f"{hwmon}/pwm1": "0", f"{hwmon}/pwm1_max": "255",
        f"{hwmon}/temp1_label": "edge", f"{hwmon}/temp1_input": "50000",
        f"{hwmon}/temp2_label": "junction", f"{hwmon}/temp2_input": "60000",
    }
    for path, text in files.items():
        with open(path, "w") as f:
            f.write(text + "\n")
    make_overdrive(dev)
    return dev, hwmon


def read(path: str) -> str:
    with open(path) as f:
        return f.read().strip()


def write(path: str, text) -> None:
    with open(path, "w") as f:
        f.write(f"{text}\n")


OD_BOOT = {"sclk": [500, 2509], "mclk": [97, 1000], "vo": 0}


def render_od(od: dict) -> str:
    return (f"OD_SCLK:\n0: {od['sclk'][0]}Mhz\n1: {od['sclk'][1]}Mhz\n"
            f"OD_MCLK:\n0: {od['mclk'][0]}Mhz\n1: {od['mclk'][1]}MHz\n"
            "OD_RANGE:\nSCLK:     500Mhz       3000Mhz\nMCLK:     674Mhz       1075Mhz\n"
            f"OD_VDDGFX_OFFSET:\n{od['vo']}mV\n")


def make_overdrive(dev: str) -> None:
    write(f"{dev}/pp_od_clk_voltage", render_od(OD_BOOT))


def fake_control(card: str, dev: str, hwmon: str):
    """An AmdGpuControl whose overdrive writes behave like the driver's: edits, then 'c' commits."""
    from rankine.tuned.gpu import AmdGpuControl

    class FakeAmdGpu(AmdGpuControl):
        staged = None

        def _od_write(self, command: str) -> None:
            od = self.overdrive()
            current = {"sclk": od["sclk"], "mclk": od["mclk"], "vo": od["voltage_offset"]}
            staged = self.staged or {k: list(v) if isinstance(v, list) else v for k, v in current.items()}
            parts = command.split()
            if parts[0] == "s":
                staged["sclk"][int(parts[1])] = int(parts[2])
            elif parts[0] == "m":
                staged["mclk"][int(parts[1])] = int(parts[2])
            elif parts[0] == "vo":
                staged["vo"] = int(parts[1])
            elif parts[0] == "c":
                write(f"{self.dev}/pp_od_clk_voltage", render_od(staged))
                staged = None
            self.staged = staged

    return FakeAmdGpu(card, dev, hwmon)
