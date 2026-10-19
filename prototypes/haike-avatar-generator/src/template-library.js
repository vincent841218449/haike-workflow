export function nativeTemplateCards(catalog, layout, motion) {
  return (catalog?.styles || []).filter(s => s.supported && s.automatic_ready === true &&
    ['adu-legacy','motiongit'].includes(s.template_ref?.runtime) && s.template_ref?.fingerprint).map(s => ({
    ...s, name:s.display_name || (/^\d\d-[A-Z]$/.test(s.id)?`${s.id} · ${s.name}`:s.name), image:s.preview, demo:s.demo,
    description:'按你的文案自动安排原包文字动效、人物画面和已上传素材；不要求固定步骤或人物数量。',
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
