import {Button} from './ui.jsx';
import './audio-check.css';

export function repairUrl(base,action) {
  const url=new URL(base,'http://local.invalid');url.searchParams.set('repair',action);url.hash='creation-voice';
  return url.pathname+url.search+url.hash;
}

export function AudioCheck({report,loading,error,onCheck,onVoice,onAudio,onTranscript,editUrl}) {
  const state=loading?'checking':report?.status||'unchecked';
  const title={checking:'正在免费核对录音',unchecked:'录音尚未核对',passed:'录音与文案已匹配',review:'录音内容需要核对',blocked:'录音与文案不匹配'}[state];
  return <section className={`audio-content-check ${state}`} aria-label="录音与文案核对" aria-busy={loading}>
    <h3 role="status">{title}</h3>
    {report&&<p className="audio-check-summary">录音 {Number(report.duration_seconds||0).toFixed(2)} 秒 · 文案 {report.script_chars} 字 · 识别 {report.recognized_chars} 字</p>}
    {error&&<p role="alert">{error}</p>}
    {report&&state!=='passed'&&<><div className="audio-check-comparison"><div><strong>文案开头</strong><p>{report.script_excerpt}</p></div><div><strong>录音识别内容</strong><p>{report.recognized_excerpt}</p></div></div>
      {!!report.critical_differences?.length&&<p>金额、数字或否定词存在差异，需要逐项核对。</p>}
      {!!report.differences?.length&&<details><summary>查看差异与识别全文</summary><ul>{report.differences.map((d,i)=><li key={i}>{d.start_ms!=null?`${(d.start_ms/1000).toFixed(2)}秒 · `:''}文案「{d.written||'无'}」／识别「{d.spoken||'无'}」</li>)}</ul><p>{report.recognized_text}</p></details>}
    </>}
    {state!=='passed'&&<><p className="helper">核对只使用本地语音识别，不生成配音或数字人。输入变化后重新核对；修改文案不会自动开始制作。</p><div className="audio-check-actions">
      {editUrl?<><Button href={repairUrl(editUrl,'voice')}>按文案配音</Button><Button href={repairUrl(editUrl,'audio')}>更换录音</Button>{report?.recognized_text&&<Button href={repairUrl(editUrl,'transcript')}>查看识别稿并修改文案</Button>}</>:<><Button onClick={onVoice}>按文案配音</Button><Button onClick={onAudio}>更换录音</Button>{report?.recognized_text&&<Button onClick={onTranscript}>查看识别稿并修改文案</Button>}</>}
      {onCheck&&<Button disabled={loading} onClick={onCheck}>{report?'重新核对':'免费核对录音'}</Button>}
    </div></>}
  </section>;
}
