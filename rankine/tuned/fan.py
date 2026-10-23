"""Software fan curve: temperature -> fan percent, with hysteresis so the fan does not hunt."""
from __future__ import annotations

MAX_POINTS = 8
HYSTERESIS = 3.0     # °C the temperature must fall before the fan slows down
PANIC_TEMP = 100.0   # junction °C at which the fan goes to 100 % whatever the curve says


def validate(points) -> list[tuple[float, float]]:
    """Checks a curve given as [[temp °C, fan %], ...]; raises ValueError with a readable reason."""
    try:
        curve = [(float(t), float(p)) for t, p in points]
    except (TypeError, ValueError):
        raise ValueError("curve must be a list of [temperature, percent] pairs") from None
    if not 2 <= len(curve) <= MAX_POINTS:
        raise ValueError(f"curve needs between 2 and {MAX_POINTS} points")
    for i, (t, p) in enumerate(curve):
        if not 0 <= t <= 110:
            raise ValueError("temperatures must be between 0 and 110 °C")
        if not 0 <= p <= 100:
            raise ValueError("fan speeds must be between 0 and 100 %")
        if i and t <= curve[i - 1][0]:
            raise ValueError("temperatures must increase from point to point")
        if i and p < curve[i - 1][1]:
            raise ValueError("fan speed must not drop as temperature rises")
    return curve


def interpolate(curve: list[tuple[float, float]], temp: float) -> float:
    if temp <= curve[0][0]:
        return curve[0][1]
    for (t0, p0), (t1, p1) in zip(curve, curve[1:]):
        if temp <= t1:
            return p0 + (p1 - p0) * (temp - t0) / (t1 - t0)
    return curve[-1][1]


class FanCurve:
    def __init__(self, points):
        self.points = validate(points)
        self.current: float | None = None

    def target(self, temp: float, junction: float | None = None) -> float:
        """Fan percent for this reading. Speeds up at once; slows down only past the hysteresis band."""
        if junction is not None and junction >= PANIC_TEMP:
            self.current = 100.0
            return self.current
        rising = interpolate(self.points, temp)
        if self.current is None or rising >= self.current:
            self.current = rising
        else:
            self.current = max(rising, min(self.current, interpolate(self.points, temp + HYSTERESIS)))
        return self.current
