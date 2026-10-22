import React from 'react';
import {AbsoluteFill,Audio,Composition,Img,OffthreadVideo,Sequence,interpolate,registerRoot,staticFile,useCurrentFrame,useVideoConfig} from 'remotion';

type Cue={text:string;startMs:number;endMs:number};
type Scene={start:number;end:number;text:string;label:string;src:string;kind:string;offset?:number};
type Props={duration:number;title:string;text:string;outputLayout:string;captions:Cue[];scenes:Scene[]};
const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'} as const;
const Orb:React.FC<{color:string;size:number;phase:number}>=({color,size,phase})=>{
  const f=useCurrentFrame();const pulse=1+Math.sin(f/42+phase)*.045;
  return <div style={{width:size,height:size,position:'relative',transform:`scale(${pulse})`}}>
    {[1,.78,.57].map((r,i)=><div key={r} style={{position:'absolute',inset:`${(1-r)*50}%`,border:`${i===0?2:1}px solid ${color}${i===0?'44':'77'}`,borderRadius:'50%',boxShadow:`0 0 ${25+i*14}px ${color}44,inset 0 0 22px ${color}44`,transform:`rotate(${f*(i%2?-.3:.4)+phase*60}deg) scaleY(${i===1?.86:1})`}}/>)}
    <div style={{position:'absolute',inset:'27%',borderRadius:'50%',background:`radial-gradient(circle at 36% 32%,#ffffffee,${color}bb 30%,${color}22 70%)`,boxShadow:`0 0 55px ${color}aa`}}/>
  </div>;
};
const Video:React.FC<Props>=p=>{
  const f=useCurrentFrame(),{fps,width,height}=useVideoConfig(),t=f/fps,wide=width>height;
  if(!p.scenes?.length)return <AbsoluteFill style={{background:'#05070b'}}/>;
  const index=Math.max(0,p.scenes.findIndex((s,i)=>f>=Math.round(s.start*fps)&&f<(i===p.scenes.length-1?Math.round(p.duration*fps):Math.round(p.scenes[i+1].start*fps))));
  const scene=p.scenes[index]||p.scenes[p.scenes.length-1];
  const startFrame=Math.round(scene.start*fps),endFrame=index===p.scenes.length-1?Math.round(p.duration*fps):Math.round(p.scenes[index+1].start*fps);
  const local=f-startFrame;
  const enter=interpolate(local,[0,24],[0,1],clamp);
  const caption=p.captions.find(c=>t*1000>=c.startMs&&t*1000<c.endMs);
  const title=scene.label||p.title;
  const head=wide?{left:100,top:65,width:1430}:{left:84,top:90,width:910};
  const panel=wide?{left:110,top:400,width:1190,height:420}:{left:86,top:840,width:908,height:550};
  const portrait=wide?{right:105,top:65,width:230,height:230}:{right:88,top:142,width:178,height:178};
  const orbY=wide?400:440;
  return <AbsoluteFill style={{background:'#05070b',color:'#f7f6f0',fontFamily:'"PingFang SC","Microsoft YaHei",sans-serif'}}>
    <AbsoluteFill style={{background:'radial-gradient(ellipse at 30% 40%,#0a203833,transparent 60%),radial-gradient(ellipse at 80% 58%,#66491422,transparent 55%)'}}/>
    <AbsoluteFill style={{opacity:.18,backgroundImage:'linear-gradient(#40506025 1px,transparent 1px),linear-gradient(90deg,#40506025 1px,transparent 1px)',backgroundSize:'80px 80px',transform:`perspective(900px) rotateX(15deg) translateY(${Math.sin(f/100)*8}px)`}}/>
    <div style={{position:'absolute',...head,display:'flex',flexDirection:'column',gap:26}}>
      <Img src={staticFile('haike-logo.png')} style={{width:210,height:60,objectFit:'contain'}}/>
      <div style={{color:'#a0a8b6',fontSize:27,letterSpacing:6}}>海客创作 · {String(index+1).padStart(2,'0')} / {String(p.scenes.length).padStart(2,'0')}</div>
      <h1 style={{margin:0,maxWidth:wide?1100:650,maxHeight:180,overflow:'hidden',fontSize:p.title.length>24?44:wide?72:64,lineHeight:1.3,fontWeight:750,textWrap:'balance',overflowWrap:'anywhere'}}>{p.title}</h1>
    </div>
    <div style={{position:'absolute',...portrait,borderRadius:'50%',overflow:'hidden',border:'3px solid #7599b799',boxShadow:'0 0 30px #79bdff33'}}><OffthreadVideo muted src={staticFile('avatar.mp4')} style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'50% 30%'}}/></div>
    <div style={{position:'absolute',left:wide?1350:100,top:orbY,width:wide?400:880,height:wide?470:280,display:'flex',flexDirection:wide?'column':'row',alignItems:'center',justifyContent:'space-around'}}>
      <Orb color="#75bcff" size={wide?220:280} phase={0}/><Orb color="#e9b649" size={wide?200:250} phase={2}/>
    </div>
    <div style={{position:'absolute',left:panel.left,top:panel.top-82,width:panel.width,display:'flex',alignItems:'center',gap:18,opacity:enter,transform:`translateY(${(1-enter)*16}px)`}}><span style={{width:9,height:9,borderRadius:9,background:'#e6b947',boxShadow:'0 0 14px #ffc559'}}/><strong style={{fontSize:wide?40:38,fontWeight:650,color:'#e4bd72',lineHeight:1.3,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{title}</strong><span style={{height:1,background:'linear-gradient(90deg,#bd8d3755,transparent)',flex:1}}/></div>
    <div style={{position:'absolute',...panel,padding:16,boxSizing:'border-box',background:'linear-gradient(140deg,#c6e6ff14,#ffffff06 50%,#e7c77914)',border:'1px solid #8397b84d',borderRadius:26,boxShadow:'0 22px 80px #0008,inset 0 1px #d4e7ff22',opacity:enter,transform:`translateY(${(1-enter)*30}px) rotateX(${(1-enter)*4}deg)`,overflow:'hidden'}}>
      <div style={{position:'relative',height:'100%',borderRadius:14,overflow:'hidden',background:'#0b1018'}}>
        <Sequence from={startFrame} durationInFrames={Math.max(1,endFrame-startFrame)} layout="none">
          {scene.kind==='video'?<OffthreadVideo muted trimBefore={Math.round((scene.offset||0)*fps)} src={staticFile(scene.src)} style={{width:'100%',height:'100%',objectFit:'contain'}}/>:<Img src={staticFile(scene.src)} style={{width:'100%',height:'100%',objectFit:'contain'}}/>}
        </Sequence>
      </div>
      <div style={{position:'absolute',left:0,right:0,top:`${((f%240)/240)*100}%`,height:2,background:'linear-gradient(90deg,transparent,#91c8ff44,transparent)'}}/>
    </div>
    <div style={{position:'absolute',left:wide?110:86,right:wide?620:86,top:wide?844:1420,display:'flex',gap:8,alignItems:'center'}}>{p.scenes.map((s,i)=><span key={s.start} style={{height:3,flex:1,background:i<index?'#c69e4c':i===index?'linear-gradient(90deg,#71baff,#dcb558)':'#ffffff16'}}/>)}</div>
    {caption&&<div style={{position:'absolute',left:wide?160:105,right:wide?160:105,top:wide?910:1490,minHeight:100,fontSize:48,lineHeight:1.55,textAlign:'center',fontWeight:650,textShadow:'0 2px 8px #000,0 0 25px #000',textWrap:'balance'}}>{caption.text}</div>}
    <Audio src={staticFile('narration.wav')}/>
  </AbsoluteFill>;
};
const defaults:Props={duration:7,title:'海客创作',text:'',outputLayout:'portrait',captions:[],scenes:[]};
const Root=()=> <Composition id="HaikeStudioAvatar" component={Video} fps={60} width={1080} height={1920} durationInFrames={420} defaultProps={defaults} calculateMetadata={({props})=>({durationInFrames:Math.max(1,Math.round(props.duration*60)),width:props.outputLayout==='landscape'?1920:1080,height:props.outputLayout==='landscape'?1080:1920})}/>;
registerRoot(Root);
