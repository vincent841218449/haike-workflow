"""Prepare a bounded local cloning excerpt; never alter narration or call AI."""
from array import array
import shutil
import sys
import wave

from backlot.work_catalog import WorkError

MAX_SOURCE_SECONDS = 600
EXCERPT_SECONDS = 20


def prepare(source, target):
    with wave.open(str(source), "rb") as audio:
        rate, frames = audio.getframerate(), audio.getnframes()
        duration = frames / rate
        if duration < 5:
            raise WorkError(f"录音只有{duration:.1f}秒，请上传至少5秒的清晰单人朗读")
        if duration > MAX_SOURCE_SECONDS:
            raise WorkError("录音超过10分钟，请选取10分钟内的录音；长于60秒会自动选取20秒片段")
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise WorkError("参考录音规范化未完成，请重新上传")
        chunk = rate // 5  # 200 ms energy windows; no speech/identity claims.
        energy, clipped = [], []
        while True:
            raw = audio.readframes(chunk)
            if not raw:
                break
            samples = array("h", raw)
            if sys.byteorder != "little":
                samples.byteswap()
            energy.append(sum(v * v for v in samples) / len(samples))
            clipped.append(sum(abs(v) >= 32760 for v in samples) / len(samples))
        if not energy or sum(energy) / len(energy) < 900:
            raise WorkError("录音接近静音，请上传声音清晰、音量正常的单人朗读")
        start, count = 0, frames
        if duration > 60:
            threshold = max(900, sorted(energy)[int(len(energy) * .9)] * .01)
            active = [int(e >= threshold) for e in energy]
            window = EXCERPT_SECONDS * 5
            sums, clips = [0], [0.0]
            for present, clipping in zip(active, clipped):
                sums.append(sums[-1] + present); clips.append(clips[-1] + clipping)
            # Prefer sustained non-silence and avoid heavily clipped sections.
            candidates = range(len(energy) - window + 1)
            best = max(candidates, key=lambda i: (sums[i + window] - sums[i]
                       - 2 * (clips[i + window] - clips[i]) + (.1 if i == 0 or not active[i - 1] else 0), -i))
            if sums[best + window] - sums[best] < 25:
                raise WorkError("长录音中未找到包含至少5秒非静音的20秒片段，请更换清晰单人录音")
            start, count = best * chunk, EXCERPT_SECONDS * rate
            audio.setpos(start)
            with wave.open(str(target), "wb") as excerpt:
                excerpt.setparams((1, 2, rate, 0, "NONE", "not compressed"))
                excerpt.writeframes(audio.readframes(count))
    if duration <= 60:
        shutil.copyfile(source, target)  # Preserve existing short-reference fingerprints.
    return {"source_duration": round(duration, 3), "duration": count / rate,
            "excerpt_start": start / rate, "excerpt_end": (start + count) / rate,
            "trimmed": duration > 60}
