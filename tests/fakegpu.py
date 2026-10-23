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
    return dev, hwmon


def read(path: str) -> str:
    with open(path) as f:
        return f.read().strip()


def write(path: str, text) -> None:
    with open(path, "w") as f:
        f.write(f"{text}\n")
