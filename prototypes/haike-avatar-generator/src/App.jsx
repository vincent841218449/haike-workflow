import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, ChevronDown, Info, Music2, Pause, Play, Settings2, Upload, X, FileText, AlertCircle, CheckCircle2 } from "lucide-react";
import { EXAMPLE_TEXT, TEMPLATES, validateInputs, availableVoicesFromAccount, defaultVoiceId } from "./generator-model.js";
import { readDraft, writeDraft } from "./draft-store.js";
import { api, upload } from "./studio-api.js";
import { ActionBar, Button, Dialog as Modal, Field, Heading, Notice, PreviewPanel, availableModels } from './ui.jsx';
import {Motion} from './Motion.jsx';
import {AvatarTemplatePicker} from './AvatarTemplatePicker.jsx';
import {TemplateExecution} from './TemplateExecution.jsx';
import {MotionGit} from './MotionGit.jsx';
import {nativeTemplateCards} from './template-library.js';
import {TemplateCover,TemplateSample} from './TemplateSample.jsx';
import {AiMaterials,AI_DEFAULTS} from './AiMaterials.jsx';
import {AvatarMaterials} from './AvatarMaterials.jsx';
import {enqueueAvatar, taskUrl, rememberSubmission, readSubmission} from './avatar-submit.js';
import {DouyinRecovery} from './DouyinRecovery.jsx';
import { VoiceLibrary, useVoiceLibrary } from './VoiceLibrary.jsx';
import {CreationStep as Step, PreparationStrip, AvatarVoiceField, AvatarPortraitField, SubmissionStatus} from './AvatarCreationFields.jsx';
import {defaultProductionTone, creationReadiness, knownAudioMismatch, materialSelection, persistedAsset} from './avatar-creation-model.js';
import './avatar-creation.css';

const samplePortrait = { name: "人物示例.png", type: "image/png" };
const assetPath = name => `${import.meta.env.BASE_URL}assets/${name}`;
const initial = () => {const q=new URLSearchParams(location.search),style=q.get('style');return { templateId: TEMPLATES.some(t=>t.id===q.get('template'))?q.get('template'):TEMPLATES[2].id, text: '', soundMode: 'voice', audio: null, portrait: null, voiceId: 'haike/cosyvoice', toneId:q.get('tone')||'', rate: 1, title: "", subtitles: true,ai:{...AI_DEFAULTS,enabled:true},motion:style?{style,layout:q.get('layout')==='landscape'?'landscape':'portrait'}:null };};
function useAssetUrl(asset, fallback) {
  const [url, setUrl] = useState(fallback);
  useEffect(() => {
    if (!(asset?.file instanceof Blob)) { setUrl(asset?.url || fallback); return; }
    const next = URL.createObjectURL(asset.file);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [asset, fallback]);
  return url;
}

export function App() {
  if(new URLSearchParams(location.search).get('mode')==='motiongit')return <MotionGit/>;
  return new URLSearchParams(location.search).get('mode') === 'motion' ? <Motion/> : <BasicAvatar/>;
}
function BasicAvatar() {
  const voiceLibrary = useVoiceLibrary();
  const [auditionTone, setAuditionTone] = useState('');
  const [serverDraft, setServerDraft] = useState(null);
  const [storyboard,setStoryboard]=useState(null),[motionCard,setMotionCard]=useState(null);
  const [motionError,setMotionError]=useState(''),[templateReload,setTemplateReload]=useState(0);
  const [quote, setQuote] = useState(null), [job, setJob] = useState(null);
  const uploaded = useRef(new WeakMap());
  const pendingSubmission = useRef(null), submissionBusy = useRef(false);
  const materialBusy = useRef(false);
  const [uncertain, setUncertain] = useState(false);
  const [submitPhase, setSubmitPhase] = useState(''), [uploading, setUploading] = useState(null);
  const [layout, setLayout] = useState({ title_size: 60, accent: "#316dd6" });
  const [input, setInput] = useState(initial);
  const currentMotion=!!input.motion && !!motionCard && motionCard.id===input.motion.style && motionCard.choice.motion.layout===input.motion.layout;
  const motionName=currentMotion?motionCard.name:'';
  const [voices, setVoices] = useState([]);
  const [voiceStatus, setVoiceStatus] = useState("loading");
  const [accountState, setAccountState] = useState(null);
  const [connectionVersion, setConnectionVersion] = useState(0);
  const [modal, setModal] = useState(null);
  const [more, setMore] = useState(()=>location.hash==='#more-fields');
  const [playing, setPlaying] = useState(false);
  const [toast, setToast] = useState("");
  const [error, setError] = useState(null);
  const [importing, setImporting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [draftLoading, setDraftLoading] = useState(true);
  const textUpload = useRef(null), audioUpload = useRef(null), textArea = useRef(null), audio = useRef(null);
  const audioTicket = useRef(0), imageTicket = useRef(0), textTicket = useRef(0);
  const templateGrid = useRef(null);
  const template = TEMPLATES.find(t => t.id === input.templateId) || TEMPLATES[2];
  const selectedSample=input.motion?(currentMotion?motionCard:null):{...template,image:assetPath(template.poster),demo:template.sample?assetPath(template.sample):null};
  const selectedTone = voiceLibrary.data?.items.find(v => v.id === input.toneId);
  const audioUrl = useAssetUrl(input.audio, assetPath("narration.wav"));
  const portraitUrl = useAssetUrl(input.portrait, assetPath("presenter.png"));
  const update = patch => { setInput(previous => ({ ...previous, ...patch })); setSaved(false); setError(null); setQuote(null); };
  const updateLayout = patch => {setLayout(old=>({...old,...patch}));setSaved(false);setQuote(null);setError(null);};
  useEffect(() => {
    if (draftLoading || !voiceLibrary.data) return;
    const defaultTone = defaultProductionTone(voiceLibrary.data, voices);
    if (defaultTone) setInput(old => old.toneId ? old : {...old, toneId:defaultTone.id, voiceId:defaultTone.model||'haike/cosyvoice'});
  }, [voiceLibrary.data, voices, draftLoading]);
  useEffect(()=>{
    const tone=new URLSearchParams(location.search).get('tone');
    const voice=voiceLibrary.data?.items.find(v=>v.id===tone);
    if(!draftLoading&&voice?.model&&input.toneId===tone&&input.voiceId!==voice.model)
      setInput(old=>({...old,voiceId:voice.model,soundMode:'voice'}));
  },[voiceLibrary.data,draftLoading,input.toneId,input.voiceId]);
  useEffect(() => {
    const controller = new AbortController();
    setAccountState(null); setVoices([]);
    fetch("/api/studio/account", { signal: controller.signal }).then(async r => { const value=await r.json(); if (!r.ok) throw Object.assign(new Error(typeof value.detail==='string'?value.detail:'暂时无法读取模型能力，请稍后刷新。'), {fromGateway:true}); return value; }).then(data => {
      setAccountState(data);
      const available = availableVoicesFromAccount(data);
      setVoices(available); setVoiceStatus(available.length ? "ready" : "empty");
      setInput(old=>({...old,voiceId:defaultVoiceId(old.voiceId,available)}));
    }).catch(e => { if (e.name !== "AbortError") {setVoiceStatus("offline");setAccountState({error:true,message:e.fromGateway?e.message:'暂时无法连接API服务，文案和素材仍可保存；请稍后重新检查连接。'});} });
    return () => controller.abort();
  }, [connectionVersion]);
  useEffect(() => {
    let live = true;
    const id = new URLSearchParams(location.search).get('draft');
    const fromServer = async id => {const d=await api(`/api/studio/drafts/${id}`);if(live){setServerDraft(d);setLayout(d.layout);const pending=readSubmission(sessionStorage,id);if(pending){pendingSubmission.current=pending;setUncertain(true);}}try{const r=await api(`/api/studio/drafts/${id}/avatar-job`);if(live){setJob(r.job);if(pendingSubmission.current&&r.job?.parent_job_id===`studio-${pendingSubmission.current.quote.revision}`){pendingSubmission.current=null;rememberSubmission(sessionStorage,null);setUncertain(false);}}if(!r.job){const p=await api(`/api/studio/drafts/${id}/ai-preview`);if(live)setStoryboard(p.plan);}}catch{}return {version:1,input:{...d.input,templateId:d.template_id,text:d.text,title:d.title}};};
    const q=new URLSearchParams(location.search);
    const restore = id ? fromServer(id) : q.has('new')||q.has('style')||q.has('template')?Promise.resolve(null):readDraft().then(d=>d?.studioDraftId?fromServer(d.studioDraftId):d);
    restore.then(draft => {
      if (!live || !draft) return;
      if (draft.version !== 1 || !draft.input || typeof draft.input.text !== "string" || !TEMPLATES.some(t => t.id === draft.input.templateId)) throw new Error();
      const tone = new URLSearchParams(location.search).get('tone');
      setInput(old=>({ ...initial(), ...draft.input, voiceId: tone?'haike/cosyvoice':draft.input.voiceId?.startsWith('haike/')?draft.input.voiceId:old.voiceId, toneId:tone||draft.input.toneId||old.toneId, soundMode:tone?'voice':draft.input.soundMode })); setSaved(!tone); setToast(tone?"已载入所选音色，原文案和图片已保留。":"已恢复保存的制作项目。");
    }).catch(() => { if (live) setToast("未能读取本地草稿，你可以继续填写并重新保存。"); }).finally(() => { if (live) setDraftLoading(false); });
    return () => { live = false; };
  }, []);
  useEffect(()=>{
    setMotionCard(null);setMotionError('');if(!input.motion)return;let live=true;
    api(`/api/studio/motion/catalog?layout=${input.motion.layout}`).then(c=>{
      if(!live)return;
      const card=nativeTemplateCards(c,input.motion.layout,input.motion).find(s=>s.id===input.motion.style);
      if(!card)throw new Error('所选模板暂不可用，请重新选择；文案与素材已保留。');
      if(input.templateRef&&input.templateRef.fingerprint!==card.choice.templateRef.fingerprint)throw new Error('所选模板版本已更新，请重新选择以使用当前版本；原内容已保留。');
      setMotionCard(card);
    }).catch(e=>{if(live)setMotionError(e.message);});
    return()=>{live=false;};
  },[input.motion?.style,input.motion?.layout,input.templateRef,templateReload]);
  useEffect(()=>{if(!serverDraft||!job)return;const revision=Number(job.parent_job_id?.replace('studio-',''));api(`/api/studio/drafts/${serverDraft.id}/storyboard${Number.isInteger(revision)&&revision>0?'?revision='+revision:''}`).then(r=>setStoryboard(r.plan)).catch(()=>{});},[job?.status,job?.stage,serverDraft?.id]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 6000);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => { audio.current?.pause(); setPlaying(false); }, [audioUrl, input.soundMode]);
  useEffect(() => {
    const grid = templateGrid.current;
    if (!grid) return;
    const showSelected = () => {
      if (grid.scrollWidth > grid.clientWidth) {
        const selected = grid.querySelector(".selected");
        if (selected) grid.scrollLeft = selected.offsetLeft - grid.offsetLeft;
      }
    };
    showSelected();
    const observer = new ResizeObserver(showSelected);
    observer.observe(grid);
    return () => observer.disconnect();
  }, [input.templateId]);
  async function importText(event) {
    const file = event.target.files?.[0]; event.target.value = "";
    if (!file) return;
    if (!/\.(txt|docx)$/i.test(file.name) || file.size > 5 * 1024 * 1024) { setError({ field: "text", message: "请上传 5 MB 以内的 DOCX 或 TXT 文案。" }); return; }
    const ticket = ++textTicket.current; setImporting(true);
    try {
      let text;
      if (/\.docx$/i.test(file.name)) {
        const mammoth = await import("mammoth/mammoth.browser.js");
        const result = await (mammoth.default || mammoth).extractRawText({ arrayBuffer: await file.arrayBuffer() });
        text = result.value.trim();
      } else {
        const bytes = await file.arrayBuffer();
        try { text = new TextDecoder("utf-8", { fatal: true }).decode(bytes); }
        catch { text = new TextDecoder("gb18030").decode(bytes); }
        text = text.replace(/^\uFEFF/, "").trim();
      }
      if (!text) throw new Error("empty");
      if ([...text].length > 5000) throw new Error("long");
      if (ticket === textTicket.current) { update({ text }); setToast(`已导入 ${file.name}，可以继续修改文案。`); }
    } catch (e) {
      if (ticket === textTicket.current) setError({ field: "text", message: e.message === "long" ? "口播文案最多5,000字，请精简后重新上传。" : "无法读取这份文案，请检查文件，或复制正文粘贴到文案框。" });
    } finally { if (ticket === textTicket.current) setImporting(false); }
  }
  async function importAudio(event) {
    const file = event.target.files?.[0]; event.target.value = "";
    if (!file) return;
    if (!/\.(wav|mp3|m4a|ogg)$/i.test(file.name) || file.size > 50 * 1024 * 1024) { setError({ field: "audio", message: "请上传 50 MB 以内的 WAV、MP3、M4A 或 OGG 音频。" }); return; }
    const ticket = ++audioTicket.current;
    const url = URL.createObjectURL(file), probe = new Audio();
    try {
      const duration = await new Promise((resolve, reject) => {
        probe.onloadedmetadata = () => resolve(probe.duration);
        probe.onerror = reject; probe.src = url;
      });
      if (!Number.isFinite(duration) || duration <= 0 || duration > 120) throw new Error();
      if (ticket === audioTicket.current) { update({ audio: { name: file.name, type: file.type, duration, file }, soundMode: "audio" }); setModal(null); setToast("音频已就绪，将直接用于制作，无需重复生成配音。"); }
    } catch { if (ticket === audioTicket.current) setError({ field: "audio", message: "音频无法播放或超过120秒，请使用可播放的口播音频。" }); }
    finally { probe.src = ""; URL.revokeObjectURL(url); }
  }
  async function importPortrait(file) {
    if (!file) return;
    if (!/\.(jpg|jpeg|png)$/i.test(file.name) || !["image/jpeg", "image/png"].includes(file.type) || file.size > 10 * 1024 * 1024) { setError({ field: "portrait", message: "请上传 10 MB 以内的 JPG 或 PNG 人物图片。" }); return; }
    const ticket = ++imageTicket.current, url = URL.createObjectURL(file);
    try {
      const img = new Image(); img.src = url; await img.decode();
      if (Math.min(img.naturalWidth, img.naturalHeight) < 256) throw new Error();
      if (ticket === imageTicket.current) { update({ portrait: { name: file.name, type: file.type, file } }); setToast("图片已载入。请确保人物正面清晰、没有严重遮挡。"); }
    } catch { if (ticket === imageTicket.current) setError({ field: "portrait", message: "图片无法读取或尺寸过小，请上传宽高至少 256 像素的图片。" }); }
    finally { URL.revokeObjectURL(url); }
  }
  async function playAudio() {
    if (playing) { audio.current.pause(); setPlaying(false); return; }
    try { await audio.current.play(); setPlaying(true); }
    catch { setToast("音频未能播放，请重新选择文件后再试。"); }
  }
  async function persistServer(values=input) {
    await writeDraft(values, serverDraft?.id);
    let d=await api('/api/studio/drafts',{id:serverDraft?.id,revision:serverDraft?.revision,template_id:values.templateId,title:values.title||values.text.split(/[。！？\n]/)[0].slice(0,16),text:values.text,layout,input:{soundMode:values.soundMode,voiceId:values.voiceId,...(values.toneId?{toneId:values.toneId}:{}),rate:values.rate,subtitles:values.subtitles,ai:values.ai||AI_DEFAULTS,motion:values.motion||null,templateRef:values.templateRef||null,music:values.music||{mode:'none'},templatePolicy:'strict',templateExecution:values.templateExecution||'native'}});
    setServerDraft(d);
    const draftUrl=new URL(location.href);draftUrl.searchParams.set('draft',d.id);draftUrl.searchParams.delete('new');history.replaceState(null,'',draftUrl);
    const assets={};
    for (const [name,kind,sample] of [['audio','audio','narration.wav'],['portrait','image','presenter.png']]) {
      const value=values[name]; if(!value || (name==='audio'&&values.soundMode!=='audio'))continue;
      if(value?.id&&serverDraft){assets[name]=persistedAsset(value);continue;}
      let file=value?.file;
      if(!file&&name==='audio')throw new Error('请上传与文案一致的口播录音，或切换为音色配音；项目样音仅供试听。');
      if(!file){const r=await fetch(assetPath(sample));if(!r.ok)throw new Error('示例素材无法读取，请上传自己的文件');file=new File([await r.blob()],value?.name||sample,{type:value?.type});}
      const cached=uploaded.current.get(file);
      const a=cached?.draftId===d.id?cached.asset:await upload(d.id,file,kind);
      uploaded.current.set(file,{draftId:d.id,asset:a});assets[name]={...a,duration:value?.duration,type:value?.type};
    }
    d=await api('/api/studio/drafts',{...d,input:{...d.input,...assets}});setServerDraft(d);
    const next={...values,...Object.fromEntries(Object.entries(assets).map(([name,value])=>[name,{...values[name],...value}]))};setInput(next);await writeDraft(next,d.id);setSaved(true);return d;
  }
  async function saveDraft(){setSaving(true);setError(null);try{await persistServer();setToast('草稿已保存，返回数字人口播页可继续编辑。');}catch(e){setError({field:'draft',message:e.message});}finally{setSaving(false);}}
  async function importMaterials(files) {
    if (materialBusy.current) throw new Error('正在上传素材，请等待当前上传完成。');
    const selected = materialSelection(files, input.ai?.materials?.length || 0);
    if (!selected.length) return;
    materialBusy.current = true;
    setSaving(true);
    let completed = 0;
    try {
      let d = await persistServer();
      for (const file of selected) {
        setUploading({completed, total:selected.length, name:file.name});
        const a = await upload(d.id, file, /\.(mp4|mov)$/i.test(file.name) ? 'video' : 'image');
        const ai = {...AI_DEFAULTS, ...d.input.ai, enabled:true, materials:[...(d.input.ai?.materials || []),
          {id:a.id, name:a.name, kind:a.kind, url:a.url, offset:0, mode:'prefer', note:'', rights_confirmed:false}]};
        d = await api('/api/studio/drafts', {...d, input:{...d.input, ai}});
        setServerDraft(d); setInput(old => ({...old, ai}));
        completed++;
      }
      setSaved(true); setStoryboard(null); setToast(`已保存${completed}份素材，系统会自动安排画面。`);
    } catch (e) {
      throw new Error(`${completed ? `已保留${completed}份上传素材。` : ''}${e.message}`);
    } finally {materialBusy.current=false;setUploading(null); setSaving(false);}
  }
  async function importMaterial(file) {return importMaterials([file]);}
  function focusProblem(problem) {
    setError(problem);
    const field = problem.field === 'audio' ? 'voice' : problem.field;
    if (field === 'template') setMore(true);
    requestAnimationFrame(() => {
      const section = document.querySelector(`[data-avatar-field="${field}"]`);
      section?.scrollIntoView({block:'center', behavior:'auto'});
      const target = section?.querySelector(field === 'text' ? 'textarea' : field === 'materials' ? 'input[type="checkbox"]' : 'button:not(:disabled),input:not([hidden]):not(:disabled)');
      (target || section)?.focus({preventScroll:true});
    });
  }
  async function planPreview(){setSaving(true);setError(null);try{const d=await persistServer();const r=await api(`/api/studio/drafts/${d.id}/ai-preview`,{revision:d.revision,confirmed:true});setStoryboard(r.plan);setToast('AI分镜建议已生成；实际时间将在声音就绪后对齐。');}catch(e){setError({field:'ai',message:e.message});}finally{setSaving(false);}}
  async function confirmGeneration() {
    if (submissionBusy.current) return;
    const problem = pendingSubmission.current ? null : knownAudioMismatch(input, job) ? {field:'voice',message:'这份录音与文案不一致，请按文案配音或替换录音。'} : validateInputs(input, voices, voiceLibrary.data?.items || []);
    if (problem) { focusProblem(problem); return; }
    submissionBusy.current=true;
    audio.current?.pause(); setPlaying(false); setSaving(true);setError(null);
    try {
      if (!pendingSubmission.current) {
        setSubmitPhase('保存内容…');
        const d=await persistServer();
        setSubmitPhase('准备制作…');
        const q=await api(`/api/studio/drafts/${d.id}/quote`,{revision:d.revision});
        setQuote(q); pendingSubmission.current={draft:d,quote:q,billingPolicy:'actual_usage',resumeTask:new URLSearchParams(location.search).get('resume_task')||(!['queued','running','paused'].includes(job?.status)?job?.job_id:undefined)};
        rememberSubmission(sessionStorage,pendingSubmission.current);
      }
      setSubmitPhase(uncertain ? '恢复原提交…' : '加入队列…');
      const j=await enqueueAvatar(api,pendingSubmission.current);
      pendingSubmission.current=null;rememberSubmission(sessionStorage,null);setUncertain(false);setJob(j);
      window.location.assign(taskUrl(j));
    } catch(e) {
      if(!e.submissionUncertain) {pendingSubmission.current=null;rememberSubmission(sessionStorage,null);}
      setUncertain(!!e.submissionUncertain);setError({field:'api',message:e.message});
    } finally {submissionBusy.current=false;setSaving(false);setSubmitPhase('');}
  }
  useEffect(()=>{if(!job||!(['queued','running'].includes(job.status)||job.status==='ambiguous'&&job.error?.code==='provider_pending'))return;const timer=setInterval(()=>api(`/api/production-queue/jobs/${job.job_id}`).then(setJob).catch(e=>setError({message:e.message})),2500);return()=>clearInterval(timer);},[job?.job_id,job?.status]);
  async function retry(){setSaving(true);try{setJob(await api(`/api/production-queue/jobs/${job.job_id}/retry`,{}));}catch(e){setError({message:e.message});}finally{setSaving(false);}}
  async function skipDouyin(){setSaving(true);try{setJob(await api(`/api/studio/ai/jobs/${job.job_id}/skip-douyin`,{confirmed:true}));}catch(e){setError({message:e.message});}finally{setSaving(false);}}
  const seconds = Math.round(input.audio?.duration || 0);
  const audioTime = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  const models = availableModels(accountState);
  const blocked = accountState === null ? '正在读取模型能力…' : accountState.error ? accountState.message || '暂时无法验证模型能力' : accountState.local_avatar?.enabled&&!accountState.local_avatar.ready ? '稳定版数字人尚未配置本机服务凭据，请联系管理员' : !models.has('haike/avatar') ? '数字人模型尚未开通' : input.soundMode==='voice'&&selectedTone?.production_ready===false ? '已选系统音色，配音服务待接通；可以试听并保存草稿' : (input.subtitles||input.ai?.enabled) && !accountState.local_asr?.ready && !models.has('haike/tencent-asr') ? '字幕识别尚未开通' : '';
  const templateBlocked=input.motion ? motionError || (!currentMotion?'正在核对所选模板…':'') : '';
  const inProgress = ['queued','running'].includes(job?.status) || job?.status==='ambiguous' && job?.error?.code==='provider_pending';
  const readiness = creationReadiness(input, voices, voiceLibrary.data?.items || [], job);
  const audioMismatch = knownAudioMismatch(input, job);
  const fallbackTone = defaultProductionTone(voiceLibrary.data, voices);
  const fieldError = field => error?.field === field || (field === 'voice' && error?.field === 'audio') ? error.message : field==='voice'&&audioMismatch ? '这份录音与文案不一致，请按文案配音或替换录音。' : '';
  const chooseTone = voice => {update({voiceId:voice.model||'haike/cosyvoice',toneId:voice.id,soundMode:'voice'});setModal(null);};
  return <main className="workspace creation-workspace avatar-creation">
    <Heading title="数字人口播" helper="给文案一个声音，让你的数字人开口讲。"><div className="creation-header-actions"><Button href="/tasks" variant="text">创作任务<ArrowRight size={15}/></Button>{serverDraft&&<Button href="/avatar?new=1">新建视频</Button>}</div></Heading>
    {blocked&&!blocked.startsWith('已选系统')&&<div className="creation-connection"><Notice message={blocked} error={accountState!==null}><Button variant="text" disabled={accountState===null} onClick={()=>{setConnectionVersion(v=>v+1);voiceLibrary.reload();}}>重新检查连接</Button><a href="/settings">查看 API 设置<ArrowRight size={14}/></a></Notice></div>}
    <AvatarTemplatePicker templateId={input.templateId} motion={input.motion} selectedName={motionName} disabled={!!(saving||draftLoading||uncertain||uploading||importing)} onChoose={async choice=>{const next={...input,...choice,ai:{...AI_DEFAULTS,...input.ai,enabled:choice.motion?true:input.ai?.enabled||false}};update(next);setStoryboard(null);setSaving(true);try{await persistServer(next);setToast("口播模板已选择并保存，原文案和素材已保留。");}catch(e){setError({field:"template",message:e.message});}finally{setSaving(false);}}}/>
    {input.motion&&<TemplateExecution motion={input.motion} value={input.templateExecution||'native'} modes={motionCard?.execution_modes} profiles={motionCard?.style_profiles} profile={input.motion.profile||''} onProfileChange={profile=>update({motion:{...input.motion,profile}})} disabled={saving||draftLoading||uncertain} onChange={templateExecution=>update({templateExecution,motion:{...input.motion,profile:templateExecution==='components'?input.motion.profile||'':''}})} music={input.music}/>}
    <PreparationStrip state={readiness}/>
    <div className="editor-shell avatar-editor"><section className="editor-content" aria-label="填写制作内容" aria-busy={draftLoading}>
      <fieldset className="avatar-form" disabled={saving||draftLoading||uncertain}>
      <div className="avatar-fields">
        <Step number="1" field="text" ready={readiness.fields[0].ready} error={fieldError('text')} title="口播文案" helper="粘贴你想说的话，也可以导入文档" className="text-step" action={<div className="upload-text"><Button disabled={importing||draftLoading} loading={importing} onClick={()=>textUpload.current.click()}><Upload size={14}/>导入文案</Button></div>}>
          <label className="sr-only" htmlFor="script-text">口播文案</label><div className="textarea-wrap"><textarea id="script-text" ref={textArea} value={input.text} disabled={draftLoading||importing} onChange={e=>update({text:e.target.value})} placeholder="在这里粘贴口播文案，系统会自动完成配音、数字人口型与画面编排…" aria-invalid={!!fieldError('text')} aria-describedby={fieldError('text')?'error-text':undefined}/><small className="character-count">{[...input.text].length.toLocaleString()} / 5,000 字</small></div>
        </Step>
        <Step number="2" field="voice" ready={readiness.fields[1].ready} error={fieldError('voice')} title={input.soundMode==='audio'?'口播声音':'配音音色'} helper="选一个适合这条视频的声音" className="sound-step">
          {audioMismatch&&<Button onClick={()=>update({soundMode:'voice'})}>按文案配音<ArrowRight size={15}/></Button>}
          {input.soundMode==='audio' ? <><div className="audio-row"><div className="audio-file"><Music2 size={20}/><div><strong>{input.audio?.name||'尚未选择音频'}</strong><small>{audioTime}</small></div></div><Button onClick={playAudio} disabled={!input.audio} aria-label={playing?'暂停音频':'播放音频'}>{playing?<Pause size={16}/>:<Play size={16}/>}</Button><Button onClick={()=>setModal('audio')}>选择 / 上传音频</Button></div><p className="helper after-input">已有录音直接制作，免配音调用。</p></> :
          <AvatarVoiceField voice={selectedTone} rate={input.rate} onRateChange={rate=>update({rate})} ready={readiness.fields[1].ready} loading={voiceLibrary.loading} error={accountState?.error ? '配音连接暂不可用，其他内容可以先编辑并保存。' : voiceLibrary.error || (input.toneId && voiceLibrary.data && !selectedTone ? '原音色在当前账户中不可用，请重新选择；原文案与图片已保留。' : '')} fallback={fallbackTone} onChooseFallback={()=>chooseTone(fallbackTone)} onChoose={()=>{setAuditionTone('');setModal('voices');}} onAudition={()=>{setAuditionTone(selectedTone.id);setModal('voices');}}/>}
        </Step>
        <Step number="3" field="portrait" ready={readiness.fields[2].ready} error={fieldError('portrait')} title="数字人图片" helper="上传一张清晰的人物正面照" className="portrait-step">
          <AvatarPortraitField value={input.portrait} url={portraitUrl} busy={saving||draftLoading||uncertain} invalid={!!fieldError('portrait')} onFile={importPortrait} onRemove={()=>update({portrait:null})}/>
          {accountState?.local_avatar?.ready&&<p className="helper after-input">稳定版数字人 · 长口播自动分段，完成后合为一条视频。</p>}
        </Step>
        <Step number="4" field="materials" optional ready={!!input.ai?.materials?.length && input.ai.materials.every(m=>m.rights_confirmed)} error={fieldError('materials')} title="视频素材" helper="有想展示的产品、场景或画面？一起放进来" className="materials-step">
          <AvatarMaterials value={input.ai} busy={saving||draftLoading||uncertain} uploading={uploading} onFiles={importMaterials} onChange={ai=>{update({ai});setStoryboard(null);}}/>
        </Step>
      </div>
      <section className="more-settings"><button className="settings-toggle" onClick={()=>setMore(!more)} aria-expanded={more} aria-controls="more-fields"><ChevronDown size={18} className={more?'':'collapsed'}/><strong>更多设置</strong><span>已自动配置，可直接制作</span></button>
        {more&&<div id="more-fields" className="settings-fields">

          <div className="sound-tabs" role="group" aria-label="声音来源"><button aria-pressed={input.soundMode==="voice"} className={input.soundMode==="voice"?"active":""} onClick={()=>update({soundMode:"voice"})}>音色配音</button><button aria-pressed={input.soundMode==="audio"} className={input.soundMode==="audio"?"active":""} onClick={()=>update({soundMode:"audio"})}>使用已有音频</button></div>
          {input.motion&&<Field label="背景音乐" hint="使用所选模板的原生动作音效；可添加自己的配乐，无需另行审核。"><select value={input.music?.mode||'none'} onChange={e=>update({music:e.target.value==='none'?{mode:'none'}:{mode:'track',asset:input.music?.asset,offset:0}})}><option value="none">不使用背景音乐</option><option value="track">使用自己的音乐</option></select>{input.music?.mode==='track'&&<><input type="file" accept=".mp3,.wav,.m4a" aria-label="上传背景音乐" onChange={async e=>{const file=e.target.files?.[0];if(!file)return;setSaving(true);try{const d=await persistServer();const asset=await upload(d.id,file,'audio');update({music:{mode:'track',asset,offset:0}});}catch(e){setError({field:'music',message:e.message});}finally{setSaving(false);}}}/><small>{input.music.asset?.name||'尚未上传音乐'}</small></>}</Field>}
          <Field label="视频标题"><input value={input.title} maxLength={36} placeholder="自动取文案首句，建议16字以内" onChange={e=>update({title:e.target.value})}/></Field><div className="layout-fields"><Field label="标题字号"><select value={layout.title_size} onChange={e=>updateLayout({title_size:Number(e.target.value)})}>{[48,54,60,66].map(n=><option key={n} value={n}>{n}px</option>)}</select></Field><Field label="强调色"><input type="color" value={layout.accent} onChange={e=>updateLayout({accent:e.target.value})}/></Field></div><label className="checkbox-row"><input type="checkbox" checked={input.subtitles} onChange={e=>update({subtitles:e.target.checked})}/>显示字幕</label>
          <details><summary>素材与分镜细节（可选）</summary><AiMaterials value={input.ai} busy={saving||draftLoading} onFile={importMaterial} onPlan={planPreview} onChange={ai=>{update({ai});setStoryboard(null);}} plan={storyboard}/></details>
        </div>}
      </section>
      </fieldset>
      <SubmissionStatus phase={submitPhase} uncertain={uncertain}/>
      <div className="notice-stack avatar-notices"><Notice message={!['text','voice','portrait','materials','audio'].includes(error?.field) ? error?.message : ''} error/></div>
      {job&&<div className="job-state"><strong>{({queued:'排队中',running:'正在制作',completed:'已完成，可查看',failed:'需要处理',awaiting_human:'等待处理',ambiguous:'等待供应商返回',cancelled:'已取消',canceled:'已取消'})[job.status]||'等待处理'}</strong><p>{job.stage}</p><Button href={taskUrl(job)}>查看创作任务</Button>{job.result?.work_id&&<Button href={job?.result?.work_id?`/tasks?work=${encodeURIComponent(job.result.work_id)}`:"/tasks"}>观看成片</Button>}{job.retryable&&<Button disabled={saving} onClick={retry}>恢复原任务</Button>}{job.status==='failed'&&/抖音/.test(job.stage)&&<Button disabled={saving} onClick={skipDouyin}>跳过抖音并恢复原任务</Button>}</div>}
      <DouyinRecovery job={job} onJob={setJob}/>
    </section><PreviewPanel label="模板效果预览" metadata={input.motion?(input.motion.layout==='portrait'?'9:16':'16:9'):template.ratio}>
      {selectedSample&&<><div className="poster-frame"><TemplateCover key={selectedSample.id} template={selectedSample}/></div>{selectedSample.sourceLabel&&<p className="template-source-label">{selectedSample.sourceLabel}</p>}<p className="preview-note">{input.motion?selectedSample.description:template.sample?'现有真实样片，制作时使用你的内容。':'模板布局示意，制作时使用你的内容。'}</p>{selectedSample.demo&&<Button className="preview-play" onClick={()=>setModal('sample')}><Play size={16}/>播放所选模板样片</Button>}</>}
      {input.motion&&!selectedSample&&(motionError?<Notice message={motionError} error><Button onClick={()=>setTemplateReload(v=>v+1)}>重新读取模板</Button></Notice>:<p className="helper" role="status">正在读取所选模板预览…</p>)}
    </PreviewPanel>
    <ActionBar note={<><strong>按实际使用结算</strong>{!inProgress&&!uncertain&&(blocked||templateBlocked||!readiness.ready)?<span className="creation-action-hint">{blocked||templateBlocked||<button type="button" onClick={()=>focusProblem({field:readiness.missing[0].id,message:readiness.message})}>{readiness.message}<ArrowRight size={13}/></button>}</span>:<span>提交后自动制作，在创作任务查看进度</span>}</>}><Button disabled={saving||draftLoading||importing||uncertain} onClick={saveDraft}>{saved?'草稿已保存':'保存草稿'}</Button>{inProgress?<Button variant="primary" href={taskUrl(job)}>查看创作任务<ArrowRight size={17}/></Button>:<Button variant="primary" loading={!!submitPhase} disabled={importing||saving||draftLoading||!!(blocked||templateBlocked)&&!uncertain} onClick={confirmGeneration}>{uncertain?'恢复原提交':submitPhase||'制作视频'}<ArrowRight size={17}/></Button>}</ActionBar></div>
    <input hidden type="file" ref={textUpload} accept=".txt,.docx" onChange={importText} aria-label="文案文件"/><input hidden type="file" ref={audioUpload} accept=".wav,.mp3,.m4a,.ogg" onChange={importAudio} aria-label="音频文件"/>
    <audio ref={audio} src={audioUrl} onEnded={()=>setPlaying(false)} onError={()=>setPlaying(false)}/>
    <div className={`toast ${toast?"visible":""}`} role="status">{toast&&<><CheckCircle2 size={18}/>{toast}</>}</div>
    {modal==='sample'&&selectedSample&&<Modal title={`${selectedSample.name} · 模板样片`} wide onClose={()=>setModal(null)} footer={<Button onClick={()=>setModal(null)}>返回制作</Button>}><TemplateSample key={selectedSample.id} template={selectedSample}/></Modal>}
    {modal==="audio"&&<Modal title="上传口播录音" description="录音内容应与文案一致；已有录音无需重复配音。" onClose={()=>setModal(null)} footer={<><Button onClick={()=>setModal(null)}>取消</Button><Button variant="primary" onClick={()=>audioUpload.current.click()}><Upload size={17}/>上传音频</Button></>}><div className="library-audio"><Music2 size={24}/><span><strong>项目样音 · 仅试听</strong><small>海客介绍口播 · 6.56秒</small></span></div><audio controls preload="none" src={assetPath('narration.wav')} aria-label="试听项目样音"/><p className="helper">制作时使用你上传的录音，或选择音色按文案配音。支持WAV、MP3、M4A、OGG；50 MB以内，最长120秒。</p></Modal>}
    {modal==='voices'&&<VoiceLibrary picker library={voiceLibrary} rate={input.rate} onRateChange={rate=>update({rate})} selectedId={input.toneId} initialAudition={auditionTone} onClose={()=>setModal(null)} onChoose={voice=>{chooseTone(voice);setToast(`已选择「${voice.name}」，文案和人物图片保持原样。`);}}/>}
  </main>;
}
