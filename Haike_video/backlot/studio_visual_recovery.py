"""Read-only admission for local rendering after a completed paid avatar stage."""
import json
from pathlib import Path

from backlot.work_catalog import WorkError, sha


def ready(project, request):
    try:
        draft=request['draft'];value=draft['input'];project=Path(project).resolve()
        if value.get('templateExecution')!='auto' or not value.get('motion',{}).get('style','').startswith('motiongit-'):
            return False
        name=request['render_id']
        if Path(name).name!=name:return False
        folder=project/'renders'/name
        if folder.is_symlink() or not folder.resolve().is_relative_to(project):return False
        from backlot.studio_audio_check import generated_clock_ready
        if not generated_clock_ready(project,request):return False
        state=json.loads((folder/'gateway-state.json').read_text())
        app=json.loads((folder/'avatar-app/state.json').read_text())
        video=folder/'avatar-source.mp4'
        if (state['stages']['avatar']['job']['status']!='succeeded' or app['status']!='succeeded'
            or app['execution']!=request['avatar_execution'] or not app['chunks']
            or any(c['status']!='succeeded' for c in app['chunks'])
            or video.is_symlink() or sha(video)!=app['output_sha256']
            or sha(Path(state['prepared']['audio_path']))!=app['audio_sha256']
            or sha(Path(state['prepared']['portrait_path']))!=app['portrait_sha256']):return False
        instance=folder/'motiongit-final';root=instance/'project'
        if json.loads((instance/'haike-template-ref.json').read_text())!=request['template_ref']:return False
        preview=root/'preview.json';receipt=instance/'visual-review.json'
        review=json.loads(receipt.read_text()) if receipt.is_file() else None
        from backlot.studio_motiongit import VISUAL_REVIEW_POLICY,EXCERPT_POLICY
        excerpts=instance/'text-excerpts.json'
        current_excerpts=excerpts.is_file() and json.loads(excerpts.read_text()).get('policy')==EXCERPT_POLICY
        if review and (review['preview_sha256']!=sha(preview)
            or not review.get('approved') and review.get('review_policy')==VISUAL_REVIEW_POLICY and current_excerpts):return False
        data=json.loads(preview.read_text())
        if not data['projectHashes']:return False
        from backlot.studio_motiongit import preview_stills
        hashes={**data['projectHashes'],**preview_stills(data)}
        if not hashes:return False
        for name,identity in hashes.items():
            source=(root/name).resolve()
            if not source.is_relative_to(root.resolve()) or sha(source)!=identity:return False
        return True
    except (OSError,ValueError,KeyError,TypeError,WorkError):
        return False
