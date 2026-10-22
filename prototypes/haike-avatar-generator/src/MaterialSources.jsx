import {useEffect,useState} from 'react';
import {Film,FolderOpen,Search} from 'lucide-react';
import {api} from './studio-api.js';
import {selectedSources,changeSource} from './material-sources.js';

export function MaterialSources({value,onChange,disabled}) {
  const [status,setStatus]=useState(null);
  useEffect(()=>{let live=true;api('/api/studio/ai/status').then(s=>live&&setStatus(s)).catch(()=>{});return()=>{live=false;};},[]);
  const selected=selectedSources(value);
  return <section className="material-sources" aria-label="画面素材来源"><header><strong>画面来源</strong><span>自有素材优先，按文案匹配缺少的画面</span></header>
    <div className="material-source-options"><div className="material-source selected"><FolderOpen size={19}/><span><strong>自己的素材</strong><small>优先采用下方上传内容</small></span><span className="source-fixed">优先</span></div>
      {[['douyin','抖音匹配',Search,status?.douyin_login_confirmed?'已配置登录，制作时检查会话':'会话待检查'],['pexels','Pexels素材库',Film,'仅在你勾选后使用']].map(([id,title,Icon,hint])=><label key={id} className={`material-source ${selected.includes(id)?'selected':''}`}><Icon size={19}/><span><strong>{title}</strong><small>{status?.material_search_ready===true?hint:'片段合成验收中'}</small></span><input type="checkbox" checked={selected.includes(id)} disabled={disabled||status?.material_search_ready!==true&&!selected.includes(id)} onChange={e=>onChange(changeSource(value,id,e.target.checked))}/></label>)}
    </div><p className="helper">{status?.material_search_ready===true?'网络片段关闭原声，保留来源和采用区间。未找到合适画面时，使用所选模板的叙述镜头；登录或网络错误会明确提示。':status?.material_search_reason||'正在读取素材接入状态；未验收的合成路线不会提交收费生成。'}</p>
  </section>;
}
