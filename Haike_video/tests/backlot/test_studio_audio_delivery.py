"""Real local codecs: quiet audio improves without re-encoding the picture."""
import hashlib
import subprocess

from backlot.studio_audio_delivery import normalize
from backlot.studio_render import media_probe
from lib.ffmpeg_locator import resolve_ffmpeg_pair


def video_packets(ffmpeg,path):
    return subprocess.run([ffmpeg,'-v','error','-i',str(path),'-map','0:v:0','-c:v','copy','-f','hash','-hash','sha256','-'],capture_output=True,check=True).stdout


def test_quiet_delivery_uses_two_pass_loudness_and_preserves_video(tmp_path):
    ffmpeg,_=resolve_ffmpeg_pair();source=tmp_path/'source.mp4';output=tmp_path/'delivery.mp4'
    subprocess.run([ffmpeg,'-v','error','-y','-f','lavfi','-i','color=c=navy:s=160x240:r=30:d=5',
        '-f','lavfi','-i','sine=frequency=330:sample_rate=48000:duration=5','-af','volume=0.05',
        '-c:v','libx264','-c:a','aac','-shortest',str(source)],check=True,capture_output=True)
    before=hashlib.sha256(source.read_bytes()).hexdigest();receipt=normalize(source,output)
    assert receipt['normalized'] and receipt['paid_calls']==0 and receipt['speech_speed']==1
    assert -16.2<=float(receipt['encoded_output']['input_i'])<=-14.8
    assert float(receipt['encoded_output']['input_tp'])<=-.5
    assert video_packets(ffmpeg,source)==video_packets(ffmpeg,output)
    assert abs(media_probe(source)['duration']-media_probe(output)['duration'])<.04
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
