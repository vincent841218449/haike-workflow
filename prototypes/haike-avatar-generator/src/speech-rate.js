export const SPEECH_RATE = { min: 0.8, max: 1.5, step: 0.05, default: 1 };
export const SPEECH_RATE_PRESETS = [
  { value: 0.8, label: '舒缓' }, { value: 1, label: '标准' },
  { value: 1.2, label: '轻快' }, { value: 1.5, label: '快速' },
];
export function isSpeechRate(value=1) {
  return typeof value === 'number' && Number.isFinite(value) && value >= SPEECH_RATE.min && value <= SPEECH_RATE.max &&
    Math.abs(value * 20 - Math.round(value * 20)) < 1e-8;
}
export const speechRate = value => isSpeechRate(value) ? Math.round(value * 100) / 100 : SPEECH_RATE.default;
export const speechRateLabel = value => `${speechRate(value).toFixed(2)}×`;
export function applyAuditionRate(audio, value) {
  if (!audio) return;
  audio.preservesPitch = true;
  audio.playbackRate = speechRate(value);
}
