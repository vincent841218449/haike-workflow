"""Collect actual encoded frames and measured audio for the offline matrix.

This writes evidence, never declares visual approval or listened=true.
"""
import argparse
import json
import math
from fractions import Fraction
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backlot.studio import atomic_private
from backlot.studio_render import media_probe
from backlot.work_catalog import sha
from lib.ffmpeg_locator import resolve_ffmpeg_pair


def stream_clock(info):
    video=float(info['video']['duration']);audio=float(info['audio']['duration'])
    return {'audio_duration':audio,'av_delta_ms':round((audio-video)*1000,3),'av_clock_match':abs(audio-video)<=.08}


def collect(roots,output):
    from PIL import Image,ImageDraw
    output=output.resolve();output.mkdir(parents=True,exist_ok=True)
    ffmpeg,_=resolve_ffmpeg_pair();rows=[]
    for root in roots:
        for case in json.loads((root/'cases.json').read_text()):
            if case['status']!='completed':continue
            video=Path(case['result']['output_path']);key=case['key']
            unique=root.name+'-'+key;folder=output/unique;folder.mkdir(exist_ok=True)
            manifest=folder/'evidence.json'
            if manifest.is_file() and json.loads(manifest.read_text()).get('sha256')==sha(video):
                cached=json.loads(manifest.read_text());cached.update(stream_clock(media_probe(video)))
                atomic_private(manifest,cached);rows.append(cached);continue
            info=media_probe(video);duration=float(info['video']['duration'])
            times=sorted({round(t,3) for t in [.15,duration*.12,duration*.25,duration*.4,duration*.55,duration*.7,duration*.85,max(0,duration-.2)]})
            contact=Image.new('RGB',(1200,1000),'#e7e7e7');draw=ImageDraw.Draw(contact);stills=[]
            for index,t in enumerate(times):
                frame=folder/f'frame-{index}.jpg'
                subprocess.run([ffmpeg,'-v','error','-y','-ss',str(t),'-i',str(video),'-frames:v','1',str(frame)],check=True,capture_output=True)
                image=Image.open(frame).convert('RGB');image.thumbnail((288,460))
                x=index%4*300+(300-image.width)//2;y=index//4*500
                contact.paste(image,(x,y+28));draw.text((x,y+8),f'{key} | {t:.2f}s',fill='#222')
                stills.append({'time':t,'path':str(frame),'sha256':sha(frame)})
            contact_path=folder/'contact.jpg';contact.save(contact_path,quality=93)
            measured=subprocess.run([ffmpeg,'-hide_banner','-i',str(video),'-af','loudnorm=I=-15.5:TP=-1.2:LRA=9:print_format=json','-f','null','-'],capture_output=True,text=True,timeout=180)
            start=measured.stderr.rfind('{');audio=json.loads(measured.stderr[start:measured.stderr.find('}',start)+1])
            decode=subprocess.run([ffmpeg,'-v','error','-i',str(video),'-f','null','-'],capture_output=True,timeout=180)
            row={'key':key,'queue_root':str(root.resolve()),'job_id':case['job_id'],'video':str(video),'sha256':sha(video),**stream_clock(info),
                 'scope':case['scope'],'duration':duration,'frames':int(info['video'].get('nb_frames',round(duration*float(Fraction(info['video']['avg_frame_rate']))))),
                 'width':info['video']['width'],'height':info['video']['height'],'fps':info['video']['avg_frame_rate'],
                 'video_codec':info['video']['codec_name'],'audio_codec':info['audio']['codec_name'],'sample_rate':info['audio']['sample_rate'],
                 'full_decode':decode.returncode==0,'audio_measurement':audio,'loudness_target_met':-16<=float(audio['input_i'])<=-15 and float(audio['input_tp'])<=-.5,
                 'stills':stills,'contact':str(contact_path),'visual_review':'pending','listened':False,
                 'presentation':case.get('result',{}).get('presentation')}
            atomic_private(manifest,row);rows.append(row);print(key,row['full_decode'],audio['input_i'],audio['input_tp'],flush=True)
    atomic_private(output/'measurements.json',rows)
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('roots',nargs='+',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();collect(args.roots,args.output)
