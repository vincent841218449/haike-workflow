"""Per-video speech speed. TTS/cache stay original; preparation follows this rate."""
import math

from backlot.work_catalog import WorkError


def speech_rate(value=1):
    if (type(value) not in {int, float} or not math.isfinite(value) or not .8 <= value <= 1.5
            or abs(value * 20 - round(value * 20)) >= 1e-8):
        raise WorkError("配音语速需为0.80–1.50倍，每次调整0.05倍")
    return round(value, 2)
