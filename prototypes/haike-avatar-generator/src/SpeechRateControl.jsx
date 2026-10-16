import {useId} from 'react';
import {SPEECH_RATE, SPEECH_RATE_PRESETS, speechRate, speechRateLabel} from './speech-rate.js';
import './speech-rate.css';

export function SpeechRateControl({value=1, onChange, compact=false}) {
  const id=useId(), rate=speechRate(value);
  return <div className={`speech-rate-control ${compact?'compact':''}`}>
    <div className="speech-rate-heading"><label htmlFor={id}>配音语速</label><output htmlFor={id}>{speechRateLabel(rate)}</output><button type="button" disabled={rate===1} onClick={()=>onChange(1)} aria-label="恢复默认语速">恢复默认</button></div>
    <input id={id} type="range" min={SPEECH_RATE.min} max={SPEECH_RATE.max} step={SPEECH_RATE.step} value={rate} aria-valuetext={`${rate.toFixed(2)}倍`} onChange={e=>onChange(Number(e.target.value))}/>
    {compact ? <p className="speech-rate-help">试听同步语速，复用已保存音频。</p> : <>
      <div className="speech-rate-presets" role="group" aria-label="常用语速">{SPEECH_RATE_PRESETS.map(preset=><button type="button" key={preset.value} aria-pressed={rate===preset.value} onClick={()=>onChange(preset.value)}><span>{preset.label}</span><small>{preset.value.toFixed(2)}×</small></button>)}</div>
      <p className="speech-rate-help">试听与成片使用此语速，仅对这条视频生效。</p>
    </>}
  </div>;
}
