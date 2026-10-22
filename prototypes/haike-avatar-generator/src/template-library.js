export function nativeTemplateCards(catalog, layout, motion) {
  return (catalog?.styles || []).filter(s => s.supported && s.automatic_ready === true &&
    ['adu-legacy','motiongit'].includes(s.template_ref?.runtime) && s.template_ref?.fingerprint).map(s => ({
    ...s, name:s.display_name || (/^\d\d-[A-Z]$/.test(s.id)?`${s.id} · ${s.name}`:s.name), image:s.preview, demo:s.demo,
    description:s.template_ref.template_id==='385712'?'使用官方原生基础表达编排，保留完整字幕、人物与原声；复杂样片镜头组仍在验收。':s.template_ref.template_id==='vibrant-poster-portrait'?'按文案组合原包已适配的七种海报动效，保留人物、完整原声和字幕。':'按你的文案自动安排原包文字动效、人物画面和已上传素材；不要求固定步骤或人物数量。',
    componentsOnly:s.execution_modes?.length===1&&s.execution_modes[0]==='components',
    sourceLabel:`ADu · v${s.template_ref.version} · 自动制作`,
    sourceDetail:s.template_ref.runtime==='motiongit'?s.scope:`${s.groups.length} 个原生镜头组 · ${s.selection}`,
    ratio:layout==='portrait'?'9:16':'16:9',
    choice:{templateId:'avatar-safe-circle-v1', motion:{style:s.id,layout}, templateRef:s.template_ref, templatePolicy:'strict', templateExecution:'auto'},
    selected:motion?.style===s.id&&motion?.layout===layout,
  }));
}

// Only an editable copy can adopt a newly selected release. Frozen jobs never pass here.
export function automaticTemplateChoice(catalog, motion) {
  if(motion.style==='catalog-default')return verticalTemplateCards(catalog,motion).find(c=>c.selectable&&c.template_ref.template_id==='template-04-dark-console-portrait') || verticalTemplateCards(catalog,motion).find(c=>c.selectable) || null;
  const cards=nativeTemplateCards(catalog,motion.layout,motion);
  const current=cards.find(c=>c.id===motion.style);
  if(current)return current;
  const corresponding={'03-A':'motiongit-610-v2-5-7','04-A':motion.layout==='landscape'?'motiongit-611-v2-5-7':'motiongit-612-v2-5-7',
    'motiongit-612':'motiongit-612-v2-5-7','motiongit-612-v2-5-2':'motiongit-612-v2-5-7'};
  return cards.find(c=>c.id===corresponding[motion.style]) || null;
}

export function filterTemplateCards(cards, search) {
  const query=search.trim().toLocaleLowerCase();
  return cards.filter(t=>!query || [t.name,t.id,t.family,t.description,t.sourceLabel,...(t.aliases||[])].join(' ').toLocaleLowerCase().includes(query))
    .sort((a,b)=>Number(b.selected)-Number(a.selected));
}

// One official identity per slug. While a new release is being verified, retain
// its explicitly labelled validated release; never disable working production
// merely because an unvalidated personal package was imported.
export function verticalTemplateCards(catalog,motion) {
  const all=(catalog?.styles||[]).filter(s=>s.template_ref?.runtime==='motiongit'&&s.template_ref.layout==='portrait');
  const latest=new Map();
  for(const s of all) {
    const id=s.template_ref.template_id,old=latest.get(id);
    if(!old||s.template_ref.version.localeCompare(old.template_ref.version,undefined,{numeric:true})>0)latest.set(id,s);
  }
  const available=new Map();
  for(const s of all.filter(s=>s.supported&&s.automatic_ready)) {
    const id=s.template_ref.template_id,old=available.get(id);
    if(!old||s.template_ref.version.localeCompare(old.template_ref.version,undefined,{numeric:true})>0)available.set(id,s);
  }
  const ready=nativeTemplateCards({styles:[...available.values()]},'portrait',motion).map(s=>{
    const next=latest.get(s.template_ref.template_id);
    return next&&next.template_ref.version!==s.template_ref.version?{...s,
      sourceLabel:`ADu · 已验收 v${s.template_ref.version} · 新版 v${next.template_ref.version} 验证中`}:s;
  });
  const enabled=new Set(ready.map(s=>s.template_ref.template_id));
  const pending=(catalog?.pending_packages||[]).filter(s=>s.layout==='portrait'&&!enabled.has(s.id.replace('motiongit:adunext:',''))).map(s=>({
    ...s,image:s.preview,demo:s.demo,ratio:'9:16',description:s.reason,sourceLabel:s.version?`ADu · v${s.version} · 验证中`:'ADu · 待导入',
    external_preview_url:s.external_preview_url||s.url,selectable:false,selected:false,
  }));
  return [...ready.map(s=>({...s,selectable:true})),...pending];
}
