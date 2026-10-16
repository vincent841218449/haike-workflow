export function taskUrl(job) {
  return `/tasks?task=${encodeURIComponent(job.job_id)}`;
}

const pendingKey = 'haike-avatar-pending-submission';
export function rememberSubmission(storage, submission) {
  if (!submission) {storage.removeItem(pendingKey); return;}
  storage.setItem(pendingKey, JSON.stringify({
    draft: {id: submission.draft.id},
    quote: {id: submission.quote.id, revision: submission.quote.revision, known_max_micros: submission.quote.known_max_micros},
    ...(submission.maximum !== undefined ? {maximum: submission.maximum} : {billingPolicy:'actual_usage'}),
    resumeTask: submission.resumeTask,
  }));
}
export function readSubmission(storage, draftId) {
  try {
    const value = JSON.parse(storage.getItem(pendingKey));
    return value?.draft?.id === draftId && value.quote?.id && Number.isInteger(value.quote.revision) && (value.billingPolicy === 'actual_usage' || Number.isInteger(value.maximum)) ? value : null;
  } catch {return null;}
}

// Retrying a lost response must reuse the frozen draft revision and quote.
export async function enqueueAvatar(request, submission) {
  const {draft, quote, maximum, resumeTask} = submission;
  try {
    return await request(`/api/studio/drafts/${draft.id}/generate`, {
      revision: quote.revision, quote_id: quote.id,
      ...(maximum !== undefined ? {max_charge_micros:maximum} : {billing_policy:'actual_usage'}), confirmed: true,
      ...(resumeTask ? {resume_task:resumeTask} : {}),
    });
  } catch (error) {
    try {
      const {job} = await request(`/api/studio/drafts/${draft.id}/avatar-job`);
      if (job?.parent_job_id === `studio-${quote.revision}`) return job;
    } catch {}
    error.submissionUncertain = !error.status || error.status >= 500 || error.status === 408;
    if (error.submissionUncertain) error.message = '提交结果待确认，请点击“查询并恢复原提交”；文案和素材已保存，不会新建重复任务。';
    throw error;
  }
}
