import {Button,Field} from './ui.jsx';

export function TemplateExecution({value='native',modes=[],profiles=[],profile='',onProfileChange,disabled,onChange,music,motion}) {
  if(value==='auto')return <section className="template-execution-settings"><p className="helper">按文案自动制作 · 使用所选模板原包的组件与材质，保留完整配音和字幕，不套用固定样片的步骤或人物数量。声音方案：{music?.mode==='track'?`原声 + ${music.asset?.name||'已选配乐'}`:'原声与动作音效（无背景音乐）'}。</p><Button href={'/avatar?'+new URLSearchParams({mode:'motiongit',style:motion.style,layout:motion.layout})} disabled={disabled}>已有口播 · 高级分镜编辑</Button></section>;
  return <section className="template-execution-settings">
    <Field label="模板制作方式" hint="原生镜头组保留作者完整动作；组件编排按文案组合所选包的组件，不等同于样片镜头。">
      <select value={value} disabled={disabled} onChange={e=>onChange(e.target.value)}>
        <option value="native" disabled={modes.length>0&&!modes.includes('native')}>原生镜头组{modes.length>0&&!modes.includes('native')?' · 待验收':' · 不自动转为自适应'}</option>
        {modes.includes('components')&&<option value="components">所选模板组件编排 · 明确使用自适应</option>}
      </select>
    </Field>
    {value==='components'&&profiles.length>0&&<Field label="模板画面材质" hint="只使用当前原包提供的材质；选择后整片保持一致。"><select value={profile} disabled={disabled} onChange={e=>onProfileChange?.(e.target.value)}><option value="">按原包与内容自动安排</option>{profiles.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>}
    <p className="helper">{value==='components'?'已选择组件编排，成片会明确标记实际采用的组件路线。':'使用所选模板的原生镜头组；文案、素材或动作时长不匹配时停止并提示，不自动转为组件编排。'} 声音方案：{music?.mode==='track'?`原声 + ${music.asset?.name||'已选配乐'} + 动作音效`:'原声与动作音效（无背景音乐）'}。</p>
    <Button href={motion?.style?.startsWith('motiongit-')?'/avatar?'+new URLSearchParams({mode:'motiongit',style:motion.style,layout:motion.layout,...(motion.profile?{profile:motion.profile}:{})}):'/avatar?mode=motion'} disabled={disabled}>已有口播 · 分镜、字幕与局部素材编辑</Button>
  </section>;
}
