export const voiceLabel = voice => ({ zh: '普通话', en: '英语', yue: '粤语' })[voice.language] || '多语言';
export function canSubmitFreeClone(operation) {
  return operation?.kind === 'clone' && operation.quote?.model === 'haike/voice-clone' && operation.quote.max_charge_micros === '0';
}
export function referencePresentation(sample) {
  if (!sample) return { summary: '', notice: '', label: '原录音试听' };
  const clock = seconds => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
  if (sample.trimmed) return {
    summary: `原录音 ${clock(sample.source_duration)} · 已准备 ${sample.duration.toFixed(1)} 秒克隆片段`,
    notice: `录音超过60秒，已自动选取 ${clock(sample.excerpt_start)}–${clock(sample.excerpt_end)} 的${sample.duration.toFixed(0)}秒片段用于克隆，无需手动剪辑。下面可试听实际使用的片段。`,
    label: '实际克隆片段试听',
  };
  return { summary: `${sample.duration.toFixed(1)}秒 · 录音格式检查通过`, notice: '', label: '参考录音试听' };
}
export function filterVoices(voices, { scope = 'system', search = '', language = 'all' } = {}) {
  const term = search.trim().toLocaleLowerCase();
  return voices.filter(voice => voice.scope === scope && (language === 'all' || voice.language === language) && (!term || [voice.name, ...voice.tags, voiceLabel(voice)].join(' ').toLocaleLowerCase().includes(term)));
}
export function operationState(status) {
  return ({ queued: '排队中', submitting: '正在提交阿里百炼', running: '正在处理，完成后自动进入音色库', accepted: '音频已生成，正在恢复原音频下载', polling: '正在查询原任务', succeeded: '已完成', failed: '未完成，请检查录音或联系管理员', cancelled: '已取消', submission_unknown: '受理结果待确认，请查询原任务，避免重复创建' })[status] || '进度待查询';
}
