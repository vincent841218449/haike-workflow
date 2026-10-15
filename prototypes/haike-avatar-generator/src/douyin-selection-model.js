export function douyinRecoveryNeeded(job) {
  return ['failed','awaiting_human'].includes(job?.status) && /抖音/.test(job.stage || '');
}
