import {isSpeechRate} from './speech-rate.js';
export function canProduceVoice(voice, models) {
  return !!voice && voice.status === 'ready' && voice.production_ready !== false &&
    models.some(model => model.id === (voice.model || 'haike/cosyvoice'));
}

export function defaultProductionTone(library, models) {
  const items = library?.items || [];
  return items.find(v => v.id === library?.default_voice_id && canProduceVoice(v, models)) ||
    items.find(v => canProduceVoice(v, models));
}

export function voiceDraft(input) {
  // The creation form always speaks the supplied script. Old recordings remain in history.
  const {audio,...rest}=input;
  return {...rest,soundMode:'voice'};
}

export function creationReadiness(input, models, tones) {
  const materials = input.ai?.materials || [];
  const fields = [
    {id:'text', label:'文案', ready:!!input.text.trim() && [...input.text].length <= 5000},
    {id:'voice', label:'音色', ready:canProduceVoice(tones.find(v => v.id === input.toneId), models) && isSpeechRate(input.rate)},
    {id:'portrait', label:'人物图片', ready:!!input.portrait},
  ];
  const missing=fields.filter(v=>!v.ready);
  if(materials.length>4 || (input.ai?.enabled && materials.some(v=>!v.rights_confirmed)))
    missing.push({id:'materials',label:materials.length>4?'素材数量（最多4份）':'素材使用确认'});
  return {fields, missing, completed:fields.filter(v => v.ready).length, ready:missing.length===0,
    message:missing.length?`还需：${missing.map(v=>v.label).join('、')}`:'准备好了，可以制作'};
}

export function materialSelection(files, existingCount) {
  const selected = Array.from(files || []);
  if (selected.length + existingCount > 4) throw new Error(`最多使用4份素材，当前还可添加${Math.max(0, 4 - existingCount)}份。`);
  for (const file of selected) {
    if (!/\.(jpg|jpeg|png|mp4|mov)$/i.test(file.name) || file.size > 80 * 1024 * 1024 || file.size === 0) {
      throw new Error(`「${file.name}」无法上传，请选择80 MB以内的JPG、PNG、MP4或MOV。`);
    }
  }
  return selected;
}

export function persistedAsset(asset) {
  return Object.fromEntries(['id','name','kind','url','duration','type']
    .filter(key => asset[key] !== undefined).map(key => [key, asset[key]]));
}
