"""Offline acoustic alignment of supplied copy; no transcription/content gate."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--model-dir',type=Path,required=True)
    p.add_argument('--audio',type=Path,required=True);p.add_argument('--cues',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio,pad_or_trim
    from faster_whisper.tokenizer import Tokenizer
    model=WhisperModel(str(a.model_dir),device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
    tokenizer=Tokenizer(model.hf_tokenizer,model.model.is_multilingual,task='transcribe',language='zh')
    audio=decode_audio(str(a.audio),sampling_rate=16000);duration=len(audio)/16000
    cues=json.loads(a.cues.read_text());segments=[]
    for cue in cues:
        start=max(0,cue['startMs']/1000-.12);end=min(duration,cue['endMs']/1000+.12)
        if not 0<end-start<=30:raise ValueError('A real input sentence window must fit the local 30-second aligner')
        clip=audio[round(start*16000):round(end*16000)]
        features=model.feature_extractor(clip);frames=min(features.shape[-1]-1,model.feature_extractor.nb_max_frames)
        encoded=model.encode(pad_or_trim(features))
        tokens=tokenizer.encode(cue['text'])
        aligned=model.find_alignment(tokenizer,[tokens],encoded,frames)[0]
        words=[];pending=''
        for row in aligned:
            text=pending+row['word'];pending=''
            x,y=start+float(row['start']),start+float(row['end'])
            if y<=x:
                if words:words[-1]['text']+=text
                else:pending=text
                continue
            words.append({'text':text,'start':x,'end':min(y,duration),'probability':float(row['probability'])})
        if pending:
            if not words:raise ValueError('No acoustically aligned words')
            words[-1]['text']+=pending
        if not words:raise ValueError('No acoustically aligned words')
        if ''.join(w['text'] for w in words).replace(' ','')!=cue['text'].replace(' ',''):
            raise ValueError('The aligner did not retain the supplied text')
        segments.append({'text':cue['text'],'start':words[0]['start'],'end':words[-1]['end'],'words':words})
    with a.audio.open('rb') as f:identity=hashlib.file_digest(f,'sha256').hexdigest()
    result={'sourceMediaSha256':identity,'method':'forced-alignment',
        'tool':{'name':'faster-whisper/CTranslate2 acoustic DTW','version':importlib.metadata.version('faster-whisper')+'/'+importlib.metadata.version('ctranslate2')},
        'clock':'bound-narration-seconds','segments':segments}
    a.output.parent.mkdir(parents=True,exist_ok=True);tmp=a.output.with_suffix('.tmp')
    tmp.write_text(json.dumps(result,ensure_ascii=False));tmp.chmod(0o600);tmp.replace(a.output)


if __name__=='__main__':main()
