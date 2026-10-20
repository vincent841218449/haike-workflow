"""One-Key avatar producer. Native queue owns execution; intents own paid retries."""
from __future__ import annotations

import base64
import difflib
import hashlib
import ipaddress
import json
import math
import re
import shutil
import socket
import subprocess
from http.client import HTTPSConnection
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler, ProxyHandler
from uuid import uuid4

from backlot.studio import Studio, atomic_private
from backlot.studio_render import media_probe
from backlot.work_catalog import WorkError, sha


def key_identity(studio):
    c = studio.configuration()
    return hashlib.sha256(json.dumps([c.get("base_url"), c.get("api_key")]).encode()).hexdigest()


def renew_if_expired(sdk, quote):
    expiry=quote.get("expires_at")
    if not expiry or datetime.fromisoformat(expiry.replace("Z","+00:00"))>datetime.now(timezone.utc): return quote
    try: renewed=sdk.request("/quotes/"+quote["id"]+"/renew",{"confirmed":True})
    except Exception: raise WorkError("原报价已过期，已完成声音和素材保留；请管理员核对报价续期服务后恢复原任务", "unavailable") from None
    if any(renewed.get(k)!=quote.get(k) for k in ("id","model","price","quoted_usage","max_charge_micros")):
        raise WorkError("报价续期改变了原费用或模型快照，请重新确认；未提交新付费调用")
    return renewed


def prepare_audio(source, target, rate=1):
    from backlot.studio_speech_rate import speech_rate
    rate = speech_rate(rate)
    from lib.ffmpeg_locator import resolve_ffmpeg_pair
    ffmpeg, _ = resolve_ffmpeg_pair()
    info = media_probe(source)
    if not info.get("audio") or not 0 < info["duration"] / rate <= 120:
        raise WorkError("数字人口播音频需要在120秒内，请截取合适的口播")
    duration = math.ceil(info["duration"] / rate * 25) / 25
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(source), "-af", f"atempo={rate},apad,atrim=0:{duration}", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(target)], capture_output=True, timeout=60)
    if r.returncode: raise WorkError("无法准备数字人驱动音轨")
    return duration


def prepare_image(source, target):
    from PIL import Image, ImageOps
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((1024, 1280))
        image.save(target, quality=94)


def validate_voice(value):
    if value.get("soundMode") == "voice":
        from backlot.studio_speech_rate import speech_rate
        speech_rate(value.get("rate", 1))
    if value.get("soundMode") == "voice" and value.get("voiceId") == "haike/tencent-tts":
        raise WorkError("腾讯精品配音已移除，请重新选择 CosyVoice，或上传已有音频")
    if value.get("soundMode") == "voice" and value.get("voiceId") not in {"haike/cosyvoice", "haike/cosyvoice-system"}:
        raise WorkError("请选择网关提供的 CosyVoice 配音，或上传已有音频")
    if value.get("soundMode") == "voice" and value.get("toneId") is not None and (not isinstance(value["toneId"], str) or not re.fullmatch(r"voice_[a-z0-9_]{1,64}", value["toneId"])):
        raise WorkError("请选择音色库中的有效音色")
    if value.get('soundMode') == 'voice' and value.get('voiceId') == 'haike/cosyvoice-system':
        from backlot.studio_voices import _system_catalogue
        system = _system_catalogue()
        if value.get('toneId') not in {v['id'] for v in system.presets()}:
            raise WorkError('请选择官方系统音色，不会替换为默认配音')


def tts_input(draft):
    value = {"text": draft["text"]}
    if draft["input"].get("toneId") and draft["input"]["toneId"] != "voice_gateway_default":
        value["voice_id"] = draft["input"]["toneId"]
    return value


def validate(studio, draft):
    if studio.template(draft["template_id"])["kind"] != "avatar": raise WorkError("请选择数字人口播模板")
    value = draft["input"]
    validate_voice(value)
    from backlot.studio_storyboard import options, motion_options
    options(studio, draft, require_service=value.get('templateExecution') != 'auto')
    motion_options(draft)
    if value.get('motion'):
        music = value.get('music') or {'mode':'none'}  # Existing drafts used the visible no-BGM default.
        if not isinstance(music, dict) or music.get('mode') not in {'none', 'track'}:
            raise WorkError('请选择声音方案，未提交收费调用')
        if music['mode'] == 'track':
            studio.asset((music.get('asset') or {}).get('id'), draft['id'])
    if not draft["text"].strip() or len(draft["text"]) > 5000: raise WorkError("口播文案需要1至5,000字")
    image = value.get("portrait") or {}
    studio.asset(image.get("id"), draft["id"])
    if value.get("soundMode") == "audio":
        audio = studio.asset((value.get("audio") or {}).get("id"), draft["id"])
        if media_probe(audio)["duration"] > 120: raise WorkError("数字人口播音频最长120秒")
    elif value.get("soundMode") != "voice": raise WorkError("请选择已有音频或网关配音")
    title = draft["title"]
    maximum = 120 if value.get("motion") else 36 if draft["template_id"].startswith("avatar-template3") else 16
    if len(title) > maximum: raise WorkError(f"当前版式标题最多{maximum}字，请在排版配置中缩短")
    composer = Path(__file__).resolve().parents[1] / "remotion-composer/node_modules"
    if not composer.is_dir(): raise WorkError("缺少本地Remotion渲染依赖，尚未提交付费调用")


def quote(studio, draft):
    validate(studio, draft)
    # Verify the real author package before uploading the portrait or quoting providers.
    # Rechecked when freezing, so a stale or forged UI selection is never authority.
    from backlot.studio_template_registry import resolve
    resolve(draft)
    from backlot.studio_asr import snapshot
    asr = snapshot(studio)  # Verify real speech before avatar spending in every new creation.
    audio_check=None
    if draft['input'].get('soundMode')=='audio':
        from backlot.studio_audio_check import check_audio, require_pass
        audio_check=check_audio(studio,draft)
        require_pass(studio,draft,audio_check)
    from backlot.studio_avatar_app import snapshot as avatar_snapshot
    avatar_execution = avatar_snapshot(studio)
    sdk = studio.client()
    if draft['input'].get('soundMode') == 'voice' and draft['input'].get('voiceId') == 'haike/cosyvoice-system':
        from backlot.studio_voices import _system_catalogue
        system = _system_catalogue()
        if not any(v.get('model') == system.MODEL and v.get('status') == 'available' for v in sdk.request('/capabilities').get('items', [])):
            raise WorkError('当前配音服务尚未接通系统音色；已选音色和素材保留，请启用服务后再制作')
    identity = "studioquote-" + uuid4().hex
    folder = studio.projects_root / draft["id"] / "assets/studio-quotes" / identity
    folder.mkdir(parents=True, exist_ok=True)
    portrait = folder / "portrait.jpg"
    prepare_image(studio.asset(draft["input"]["portrait"]["id"], draft["id"]), portrait)
    prepared = {"portrait_path": str(portrait), "image_file": None if avatar_execution else sdk.upload(portrait, "image")["id"]}
    quotes = {}
    if draft["input"]["soundMode"] == "audio":
        audio = folder / "narration.wav"
        duration = prepare_audio(studio.asset(draft["input"]["audio"]["id"], draft["id"]), audio)
        prepared.update(audio_path=str(audio), duration=duration, audio_file=sdk.upload(audio, "audio")["id"] if not avatar_execution or asr['provider']=='gateway' else None)
        if not avatar_execution: quotes["avatar"] = sdk.quote("haike/avatar", {"audio_file": prepared["audio_file"], "image_file": prepared["image_file"]}, draft["id"])
        if asr["provider"] == "gateway": quotes["asr"] = sdk.quote("haike/tencent-asr", {"audio_file": prepared["audio_file"]}, draft["id"])
    else:
        quotes["tts"] = sdk.quote(draft["input"]["voiceId"], tts_input(draft), draft["id"])
        # Availability is checked before any TTS charge. Its exact avatar quote needs the real audio.
        models = {m.get("id") or m.get("model") for m in sdk.request("/capabilities").get("items", [])}
        required = (set() if avatar_execution else {"haike/avatar"}) | ({"haike/tencent-asr"} if asr["provider"] == "gateway" else set())
        if required - models: raise WorkError("数字人或字幕模型尚不可用，请由管理员确认成本费率后再制作")
    data = {"id": identity, "draft": draft, "prepared": prepared, "quotes": quotes, "asr": asr, "key_identity": key_identity(studio), "created_at": datetime.now(timezone.utc).isoformat()}
    if avatar_execution: data['avatar_execution'] = avatar_execution
    if audio_check: data['audio_check']=audio_check
    with studio.db() as db: db.execute("INSERT INTO studio_quotes VALUES(?,?)", (identity, json.dumps(data, ensure_ascii=False)))
    return public_quote(data)


def public_quote(data):
    return {"id": data["id"], "revision": data["draft"]["revision"], "known_max_micros": sum(int(q["max_charge_micros"]) for q in data["quotes"].values()),
            "needs_audio_quote": data["draft"]["input"]["soundMode"] == "voice", "ai_trial": data["draft"]["input"].get("ai", {}).get("enabled", False), "avatar_execution":data.get('avatar_execution'), "items": [{"stage": k, "model": q["model"], "max_charge_micros": q["max_charge_micros"], "billing_source": q.get("billing_source", "gateway")} for k, q in data["quotes"].items()] + ([{"stage": "asr", "model": "local/whisper", "max_charge_micros": "0"}] if data.get("asr", {}).get("provider") == "local-whisper" else [])}


def frozen_request(studio, draft, quote_id, maximum=None):
    # New submissions cannot reuse a retired-model quote. Already queued requests
    # keep their original execution state and resume through the native queue.
    validate_voice(draft["input"])
    if draft['input'].get('motion') and 'templateExecution' not in draft['input']:
        raise WorkError('请保存本次模板制作方式后重新读取报价；旧任务仍可按冻结输入恢复', 'template_incompatible')
    with studio.db() as db: row = db.execute("SELECT data FROM studio_quotes WHERE id=?", (quote_id,)).fetchone()
    if not row: raise WorkError("请先读取本次制作报价")
    data = json.loads(row[0])
    if data["draft"] != draft or data["key_identity"] != key_identity(studio): raise WorkError("内容或Key已改变，请重新读取报价")
    if draft['input'].get('soundMode')=='audio':
        from backlot.studio_audio_check import require_pass
        require_pass(studio,draft,data.get('audio_check'))
    from backlot.studio_avatar_app import snapshot as avatar_snapshot
    if data.get('avatar_execution') != avatar_snapshot(studio): raise WorkError('数字人应用配置已改变，请重新读取制作信息；未提交调用')
    from backlot.studio_billing import authorization
    billing = authorization(maximum)
    if maximum is not None and maximum < public_quote(data)["known_max_micros"]: raise WorkError("费用上限低于已读取报价，未提交任务")
    # The original gateway quote expires server-side. Do not silently replace it before charging.
    from backlot.studio_presentation import selected
    from backlot.studio_template_registry import resolve
    ref = resolve(draft)
    presentation = selected(draft)
    if ref and ref['runtime'] in {'adu-legacy','motiongit'}:
        presentation.update(template_ref=ref, adapter='motiongit' if ref['runtime']=='motiongit' else 'adu-motion-video')
    automatic = {}
    if draft['input'].get('templateExecution') == 'auto':
        from backlot.studio_template_auto import snapshot
        automatic['automatic_template_execution'] = snapshot(draft)
    return {**data, "workflow_version": 4, "template_ref": ref, "presentation":presentation, **automatic, **billing, "render_id": "studio-" + str(draft["revision"])}


def public_media_address(host, port):
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    ips = [ipaddress.ip_address(a[4][0]) for a in addresses]
    if ips and all(ip.is_global for ip in ips): return str(ips[0])
    # A local TUN fake-DNS address is not an origin address. For known public
    # media hosts only, verify public DNS over HTTPS and pin the actual socket.
    known = (
        re.fullmatch(r"dashscope-result-[a-z0-9-]+\.oss-[a-z0-9-]+\.aliyuncs\.com", host)
        or re.fullmatch(r"v[0-9]+(?:-[a-z0-9]+)+\.zjcdn\.com", host)
        or host in {"videos.pexels.com", "images.pexels.com", "rh-comfyui01.tos-cn-beijing.volces.com", "www.douyin.com"}
    )
    benchmark = ipaddress.ip_network("198.18.0.0/15")
    if not known or not ips or not all(ip.version == 4 and ip in benchmark for ip in ips):
        raise WorkError("供应商媒体地址不能指向本地网络")
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl): return None
    try:
        dns = "https://1.1.1.1/dns-query?" + urlencode({"name": host, "type": "A"})
        with build_opener(ProxyHandler({}), NoRedirect()).open(Request(dns, headers={"Accept": "application/dns-json"}), timeout=10) as response:
            raw = response.read(65537)
        if len(raw) > 65536: raise ValueError()
        data = json.loads(raw)
        answers = [ipaddress.ip_address(a["data"]) for a in data.get("Answer", []) if a.get("type") == 1]
        if data.get("Status") != 0 or not answers or not all(a.is_global for a in answers): raise ValueError()
        return str(answers[0])
    except Exception: raise WorkError("代理DNS未能核对真实公网媒体地址，请核对代理DNS后恢复原任务") from None


def media_https_handler(address):
    class PinnedConnection(HTTPSConnection):
        def connect(self):
            if self._tunnel_host: raise WorkError("媒体下载不允许额外代理隧道")
            self.sock = socket.create_connection((address, self.port), self.timeout, self.source_address)
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)
    class Handler(HTTPSHandler):
        def https_open(self, request):
            return self.do_open(PinnedConnection, request, context=self._context)
    return Handler()


def download_result(url, path, referer=None):
    # Gateway results contain supplier media only. Follow validated HTTPS redirects, with no Key headers.
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl): return None
    from urllib.error import HTTPError
    for _ in range(5):
        p = urlsplit(url)
        # Some CosyVoice receipts use HTTP OSS links. Upgrade only the known
        # output hosts; preserve signatures and keep TLS/DNS checks below.
        if p.scheme == "http" and not p.username and not p.password and p.port in {None, 80} and re.fullmatch(r"dashscope-result-[a-z0-9-]+\.oss-[a-z0-9-]+\.aliyuncs\.com", p.hostname or ""):
            url = p._replace(scheme="https", netloc=p.hostname).geturl()
            p = urlsplit(url)
        if p.scheme != "https" or p.username or p.password or not p.hostname: raise WorkError("供应商媒体地址无效")
        address = public_media_address(p.hostname, p.port or 443)
        opener = build_opener(ProxyHandler({}), NoRedirect(), media_https_handler(address))
        try:
            headers = {"User-Agent": "HaikeVideo/1.0", **({"Referer": referer} if referer else {})}
            with opener.open(Request(url, headers=headers), timeout=90) as response:
                temporary = path.with_suffix(path.suffix + ".part")
                count = 0
                with temporary.open("wb") as out:
                    while chunk := response.read(1024 * 1024):
                        count += len(chunk)
                        if count > 100 * 1024 * 1024: raise WorkError("供应商媒体超过100MB")
                        out.write(chunk)
                temporary.replace(path)
                return
        except HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}: raise WorkError("供应商媒体暂时无法下载，请恢复原任务", 'unavailable') from None
            from urllib.parse import urljoin
            url = urljoin(url, exc.headers.get("Location", ""))
    raise WorkError("供应商媒体跳转过多")


def _caption_word_groups(words, limit=18):
    units = []
    for word in words:
        word = dict(word)
        if units and re.search(r"[A-Za-z0-9]$", units[-1]["text"]) and re.match(r"^[A-Za-z0-9]", word["text"]):
            units[-1].update(text=units[-1]["text"] + word["text"], end=word["end"])
        else: units.append(word)
    groups, group = [], []
    for word in units:
        if group and sum(len(w["text"]) for w in group) + len(word["text"]) > limit:
            groups.append(group); group = []
        group.append(word)
    if group: groups.append(group)
    if len(groups) > 1 and len("".join(w["text"] for w in groups[-1]).strip(" ，。！？、；：")) < 5:
        pair = groups[-2] + groups[-1]
        choices = []
        for i in range(1, len(pair)):
            left = sum(len(w["text"]) for w in pair[:i]); right = sum(len(w["text"]) for w in pair[i:])
            if 6 <= left <= limit and 6 <= right <= limit: choices.append((abs(left-right), i))
        if choices:
            cut = min(choices)[1]; groups[-2:] = [pair[:cut], pair[cut:]]
    return groups


def captions(result, duration, split=True):
    """Sentence timing comes from ASR, never from input text/duration guesses."""
    values = result.get("segments") or result.get("sentences") or []
    if not values:
        for match in re.finditer(r"\[(\d+):(\d+(?:\.\d+)?),(\d+):(\d+(?:\.\d+)?)\]\s*([^\n]+)", result.get("text") or ""):
            values.append({"start": int(match[1]) * 60 + float(match[2]), "end": int(match[3]) * 60 + float(match[4]), "text": match[5].strip()})
    out = []
    for s in values:
        start, end, text = float(s["start"]), min(float(s["end"]), duration), str(s["text"]).strip()
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end and text): continue
        if split and s.get("words"):
            for group in _caption_word_groups(s["words"]):
                out.append({"text": "".join(w["text"] for w in group).strip(), "startMs": group[0]["start"]*1000,
                            "endMs": group[-1]["end"]*1000, "timestampMs": None, "confidence": None})
            continue
        # Short groups inside each recognised sentence; this is sentence-aligned, not word-level karaoke.
        groups = [text[i:i+18] for i in range(0, len(text), 18)] if split else [text]
        for i, group in enumerate(groups):
            out.append({"text": group, "startMs": (start+(end-start)*i/len(groups))*1000, "endMs": (start+(end-start)*(i+1)/len(groups))*1000, "timestampMs": None, "confidence": None})
    if not out: raise WorkError("语音识别没有返回可用句级时间轴，保留音频和数字人，请检查字幕阶段")
    return out


def clock_captions(result, duration):
    # GPT can select observed word boundaries even if Whisper returns a single
    # long segment. Display wrapping must not determine storyboard timing.
    if result.get("provider") != "local-whisper": return captions(result, duration, split=False)
    return [{"text": w["text"].strip(), "startMs": w["start"]*1000, "endMs": min(w["end"], duration)*1000,
             "timestampMs": None, "confidence": w.get("probability"), "clock": "word"}
            for s in result["segments"] for w in s["words"]]


def source_captions(draft, cues):
    """Correct ASR display spelling from the supplied script; keep actual cues."""
    if not cues:return cues
    if draft.get('input',{}).get('soundMode')=='voice':
        # TTS already received the source script. Recognition supplies timing,
        # never approval of that script. Missing anchors merge observed ranges
        # rather than reject speech, discard text or invent word timestamps.
        source=draft['text']
        positions=[i for i,c in enumerate(source) if c.isalnum() or c=='_']
        written=''.join(source[i] for i in positions).casefold()
        parts=[re.sub(r'[^\w\u4e00-\u9fff]','',c['text']).casefold() for c in cues]
        matcher=difflib.SequenceMatcher(None,written,''.join(parts),autojunk=False)
        mapping={b+j:positions[a+j] for a,b,size in matcher.get_matching_blocks() for j in range(size)} if len(written)==len(positions) else {}
        boundaries=[(0,0)];offset=len(parts[0])
        for index,part in enumerate(parts[1:],1):
            anchors=[mapping[i] for i in range(offset,offset+len(part)) if i in mapping]
            if anchors and boundaries[-1][1]<anchors[0]<len(source):
                boundaries.append((index,anchors[0]))
            offset+=len(part)
        boundaries.append((len(cues),len(source)))
        return [{**cues[a],'endMs':cues[b-1]['endMs'],'text':source[start:end],
                 **({'clock':'sentence'} if b-a>1 else {})}
                for (a,start),(b,end) in zip(boundaries,boundaries[1:])]
    from backlot.studio_storyboard import bind_script_ranges, verify_spoken_script
    verify_spoken_script(draft['text'], cues)
    units={'scenes':[{'from_cue':i,'to_cue':i,'script_start':0,'script_end':1} for i in range(len(cues))]}
    rows=bind_script_ranges(units,draft,cues,max_units=3000)['scenes']
    return [{**cue,'text':draft['text'][row['script_start']:row['script_end']].strip()} for cue,row in zip(cues,rows)]


def run_avatar(project_dir, request, sdk=None, *, on_progress=None):
    from backlot.production_queue import ProductionQueueCancelled
    studio = Studio(Path(project_dir).parent)
    if request["key_identity"] != key_identity(studio): raise WorkError("API Key已改变；恢复付费任务前请恢复原账户连接")
    sdk = sdk or studio.client()
    output_dir = Path(project_dir) / "renders" / request["render_id"]
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "gateway-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"stages": {}, "prepared": request["prepared"]}
    def save(): atomic_private(state_path, state)
    steps_done = 0
    draft_input = request["draft"]["input"]
    needs_clock = bool(request.get("workflow_version", 1) >= 2 or draft_input.get("subtitles", True) or draft_input.get("ai", {}).get("enabled"))
    needs_ai = bool(draft_input.get("ai", {}).get("enabled"))
    steps_total = 4 + int(needs_clock) + int(needs_ai)
    current_stage = '初始化制作'
    def publish_progress(stage, advance=False):
        nonlocal steps_done, current_stage
        current_stage = stage
        if advance: steps_done += 1
        if on_progress: on_progress(stage, steps_done, steps_total)
    def paid(stage, model, inputs):
        if request.get('local_recomposition'):
            previous=state['stages'].get(stage,{}).get('job',{})
            if previous.get('status')=='succeeded': return previous.get('result') or {}
            raise WorkError('本次只允许复用原产物重新排版；已有阶段结果缺失，未提交任何新收费调用', 'local_artifact_missing')
        replacement = (request.get('avatar_replacements') or [None])[-1] if stage == 'avatar' else None
        if replacement:
            previous = state['stages'].get(stage, {})
            if previous.get('intent_identity') != replacement['intent']:
                job = previous.get('job') or {}
                if previous.get('intent') != replacement['previous_intent'] or job.get('id') != replacement['previous_job_id'] or job.get('status') != 'submission_unknown' or job.get('upstream_id') or job.get('media_artifact_available') or (job.get('result') or {}).get('video_url'):
                    raise WorkError('原数字人请求已改变，未提交新的收费调用', 'replacement_conflict')
                state.setdefault('stage_history', []).append({'name':stage, 'stage':previous, 'replacement':replacement})
                state['stages'][stage] = {'intent_identity':replacement['intent']}
                save()  # Archive and replacement identity are one atomic file write.
        if not state['stages'].get(stage, {}).get('quote'):
            q = (None if replacement else request["quotes"].get(stage)) or sdk.quote(model, inputs, request["draft"]["id"])
            history = [h['stage'] for h in state.get('stage_history', [])]
            committed = request.get('inherited_charge_micros', 0) + sum(int(s["quote"]["max_charge_micros"]) for s in [*state["stages"].values(), *history] if s.get('quote',{}).get('max_charge_micros') is not None)
            from backlot.studio_billing import check_total
            check_total(request, committed + int(q["max_charge_micros"]))
            state['stages'].setdefault(stage, {})['quote'] = q; save()
        s = state["stages"][stage]
        if replacement and int(s['quote']['max_charge_micros']) > replacement['maximum']:
            raise WorkError('本次数字人报价已变化，未提交新调用；配音和字幕已保留', 'quote_changed')
        if not s.get("job"):
            s["quote"]=renew_if_expired(sdk,s["quote"]);save()
        if not s.get("intent"):
            identity = s.get('intent_identity') or "call_" + hashlib.sha256((request["id"] + ":" + stage).encode()).hexdigest()[:32]
            s['intent_identity'] = identity; save()
            try: s["intent"] = sdk.confirm(s["quote"], int(s["quote"]["max_charge_micros"]), identity); save()
            except (TimeoutError, OSError):
                if request.get('workflow_version', 1) >= 2:
                    raise WorkError('原请求回执暂未返回，系统将按原编号查询，无需重新提交', 'provider_pending') from None
                raise
        # A healthy avatar run can exceed ten minutes; keep polling the same intent.
        try: job = sdk.wait(s["intent"], timeout=3600 if stage == "avatar" else 600)
        except (TimeoutError, OSError):
            if request.get('workflow_version', 1) >= 2:
                raise WorkError('原模型请求查询暂时中断，系统将自动继续', 'provider_pending') from None
            raise
        s["job"] = job; save()
        result = job.get("result") or {}
        artifact_ready = (stage == "avatar" and job["status"] == "submission_unknown"
                          and job.get("media_artifact_available") is True
                          and bool(job.get("upstream_id"))
                          and isinstance(result.get("video_url"), str) and bool(result["video_url"]))
        if job["status"] != "succeeded" and not artifact_ready:
            if job["status"] in {"failed", "cancelled"}: raise WorkError("模型任务未成功，请到账户中心核对原调用明细")
            if request.get("workflow_version", 1) >= 2:
                raise WorkError("正在等待原模型请求返回；系统会自动查询，无需重复提交", "provider_pending")
            if job.get("billing_source") == "local-provider":
                raise WorkError(job.get("message") or "本地配音尚未完成，请恢复原任务", "unavailable")
            raise WorkError("原模型任务仍在处理或结果待核对，请恢复此任务；不会新建付费调用", "unavailable")
        if artifact_ready: publish_progress("数字人视频已返回，费用回执待核对")
        return result
    try:
        publish_progress("准备配音与原始音轨")
        p = state["prepared"]; draft = request["draft"]
        if request.get('audio_check'):
            from backlot.studio_audio_check import require_pass
            require_pass(studio,draft,request['audio_check'])
        if request.get('avatar_execution'):
            from backlot.studio_avatar_app import verify_execution
            verify_execution(studio,request['avatar_execution'])
        from backlot.studio_presentation import selected, verify
        if request.get('presentation'): verify(draft,request['presentation'],selection_only=True)
        if draft['input'].get('templateExecution') == 'auto':
            from backlot.studio_template_auto import snapshot
            if request.get('automatic_template_execution') != snapshot(draft):
                raise WorkError('自动模板编译器或原包已改变，原任务保留且未提交新费用', 'template_mismatch')
        if (request.get('template_ref') or {}).get('runtime') == 'motiongit':
            from backlot.studio_presentation import verify_native
            verify_native(request['presentation'],request['template_ref'])
            from backlot.studio_motiongit import precheck
            publish_progress('理解整篇原文，检查完整模板的可行表达')
            precheck(studio,draft,output_dir)
        if request.get('workflow_version', 1) >= 4 and (request.get('template_ref') or {}).get('runtime') == 'adu-legacy':
            from backlot.studio_presentation import verify_native
            from backlot.studio_motion_director import direct
            verify_native(request['presentation'], request['template_ref'])
            publish_progress('理解整篇原文，按所选原生模板编排')
            direct(studio, draft, output_dir)
        asr = request.get("asr", {"provider": "gateway"})
        if asr["provider"] == "local-whisper":
            from backlot.studio_asr import configuration, identity
            if identity(configuration(studio)) != asr["identity"]:
                raise WorkError("字幕引擎已改变，请恢复原配置后继续原任务")
        if not p.get("audio_path"):
            raw = output_dir / "tts-source.wav"
            if not raw.exists():
                result = paid("tts", draft["input"]["voiceId"], tts_input(draft))
                if result.get("audio_base64"): raw.write_bytes(base64.b64decode(result["audio_base64"], validate=True))
                else: download_result(result["audio_url"], raw)
            audio = output_dir / "narration.wav"
            duration = prepare_audio(raw, audio, draft["input"].get("rate", 1))
            p.update(audio_path=str(audio), duration=duration, audio_file=sdk.upload(audio, "audio")["id"] if not request.get('avatar_execution') or asr['provider']=='gateway' else None); save()
        publish_progress("原始音轨已就绪", True)
        cues = []
        clock_cues = []
        if needs_clock:
            publish_progress("识别真实声音与字幕时间轴")
            if asr["provider"] == "local-whisper":
                if request.get('audio_check'):
                    from backlot.studio_audio_check import production_clock
                    result=production_clock(studio,draft,request['audio_check'],p['audio_path'],p['duration'])
                    atomic_private(output_dir/'local-asr.json',{'fingerprint':{'audio_sha256':sha(Path(p['audio_path'])),'engine_identity':asr['identity']},
                                                              'result':result,'customer_charge_micros':'0','source':'audio-content-preflight'})
                else:
                    from backlot.studio_asr import transcribe
                    result = transcribe(studio, asr, Path(p["audio_path"]), output_dir, p["duration"])
            else:
                result = paid("asr", "haike/tencent-asr", {"audio_file": p["audio_file"]})
            cues = captions(result, p["duration"])
            clock_cues = clock_captions(result, p["duration"])
            if draft['input'].get('soundMode')=='voice':
                clock_cues = source_captions(draft, clock_cues)
            elif request.get("workflow_version", 1) >= 2:
                from backlot.studio_storyboard import verify_spoken_script
                verify_spoken_script(draft["text"], clock_cues)
            cues = source_captions(draft, cues)
            publish_progress("字幕时间轴已就绪", True)
        from backlot.studio_storyboard import produce
        if needs_ai: publish_progress("按文案安排模板与已上传素材" if draft['input'].get('templateExecution') == 'auto' else "理解分镜并匹配用户与网络素材")
        direction_path=output_dir/'native-direction.json'
        adaptive=direction_path.is_file() and json.loads(direction_path.read_text()).get('workflow')=='adu-source-components-v1'
        if draft['input'].get('templateExecution') == 'auto':
            from backlot.studio_template_auto import storyboard as automatic_storyboard
            storyboard = automatic_storyboard(studio,draft,output_dir,p['duration'])
        else:
            storyboard = None if adaptive else produce(studio, draft, output_dir, clock_cues, p["duration"], paid)
        if needs_ai: publish_progress("分镜与素材已就绪", True)
        from backlot.studio_preflight import prepare
        if draft["input"].get("motion"): publish_progress("检查模板、素材与真实口播时长")
        composition = prepare(studio, draft, output_dir, Path(p["audio_path"]), clock_cues, storyboard, cues if draft["input"].get("subtitles", True) or draft['input'].get('templateExecution') == 'auto' else [], legacy_variant=request.get('workflow_version', 1) <= 3)
        if composition["notice"]: publish_progress(composition["notice"])
        video = output_dir / "avatar-source.mp4"
        publish_progress("数字人生成与结果下载")
        if request.get('local_recomposition'):
            previous=state['stages'].get('avatar',{}).get('job',{})
            if not video.is_file():
                raise WorkError('原数字人缓存缺失，未提交任何新生成，请恢复原文件','local_artifact_missing')
            if request.get('avatar_execution'):
                cached=json.loads((output_dir/'avatar-app/state.json').read_text())
                if previous.get('status')!='succeeded' or cached.get('status')!='succeeded' or cached.get('output_sha256')!=sha(video):
                    raise WorkError('原数字人缓存已改变，未提交任何新生成','local_artifact_missing')
        elif not video.exists() or request.get('avatar_execution'):
            if request.get('avatar_execution'):
                from backlot.studio_avatar_app import produce as produce_avatar_app
                job = produce_avatar_app(studio,request['avatar_execution'],output_dir,Path(p['audio_path']),Path(p['portrait_path']),clock_cues,on_progress=publish_progress,
                                         billing_execution=request.get('avatar_billing_execution'),
                                         submission_reissue=request.get('avatar_submission_reissue'))
                state['stages']['avatar'] = {'execution':request['avatar_execution'], 'quote':{'model':'haike/avatar','max_charge_micros':None,'billing_source':'local-provider','billing_policy':'actual_usage'}, 'job':job}
                save()
                if job['status'] != 'succeeded':
                    if job['status']=='failed': raise WorkError(job.get('message') or '数字人应用生成失败，已保留全部产物')
                    if job['status']=='submission_unknown':
                        raise WorkError(job.get('message') or '原数字人分段提交回执不明，未重复提交','provider_reconciliation')
                    raise WorkError(job.get('message') or '数字人应用正在生成','provider_pending')
            else:
                result = paid("avatar", "haike/avatar", {"audio_file": p["audio_file"], "image_file": p["image_file"]})
                download_result(result["video_url"], video)
        publish_progress("数字人画面已就绪", True)
        from backlot.studio_composition import compose_avatar
        actual_presentation=selected(draft)
        if composition['mode']=='adu-components':
            from backlot.studio_adu_components import compose
            publish_progress('使用所选03-A原包组件合成并核验')
            result=compose(studio,draft,output_dir,video,Path(p['audio_path']),composition['component_plan'])
            publish_progress('成片核验完成，正在登记作品',True)
            return result
        if composition['mode'] == 'motiongit':
            from backlot.studio_motiongit import compose
            from backlot.studio_presentation import verify_native
            result=compose(studio,draft,output_dir,video,Path(p['audio_path']),cues if draft['input'].get('subtitles',True) or draft['input'].get('templateExecution')=='auto' else [],composition['segments'],on_progress=on_progress)
            verify_native(result.get('result',{}).get('presentation'),request['template_ref'],rendered=True)
            verify(draft,result['result']['presentation'])
            result['result'].update(composition_mode='motion',requested_presentation=request['presentation'])
            return result
        if composition['mode'] == 'instrument':
            from backlot.studio_composition import compose_instrument
            publish_progress('按仪器台演示合成蓝金光球、玻璃面板与本期素材')
            actual_presentation=composition['presentation']
            verify(draft,actual_presentation)
            output=compose_instrument(output_dir,draft,video,Path(p['audio_path']),p['duration'],cues if draft['input'].get('subtitles',True) else [],storyboard,actual_presentation)
        if composition["mode"] == "motion":
            from backlot.studio_storyboard import compose_motion
            publish_progress("渲染动效画面、字幕与配乐")
            try:
                result = compose_motion(studio, draft, output_dir, video, Path(p["audio_path"]), clock_cues, storyboard, caption_cues=cues if asr["provider"] == "local-whisper" else None)
            except WorkError as exc:
                raise WorkError('所选模板合成未完成，声音与数字人已保留，不会改用其他模板。'+str(exc)[:300], 'template_incompatible') from exc
            if result.get("status") == "completed":
                if (request.get('template_ref') or {}).get('runtime') == 'adu-legacy':
                    from backlot.studio_presentation import verify_native
                    verify_native(result.get('result', {}).get('presentation'), request['template_ref'], rendered=True)
                elif not result.get('result', {}).get('presentation'):
                    result.setdefault('result', {})['presentation'] = {**actual_presentation,'variant':'original','variant_name':'原版镜头组','adapter':'adu-motion-video'}
                result.setdefault('result', {}).update(composition_mode='motion',requested_presentation=request.get('presentation') or selected(draft))
                verify(draft,result['result']['presentation'])
                publish_progress("动效画面已合成", True)
                publish_progress("成片核验完成，正在登记作品", True)
                return result
            raise WorkError('所选模板渲染尚未通过，原产物已保留，不会改用基础口播', 'template_incompatible')
        effective = composition["draft"]
        if composition['mode']=='basic':
            publish_progress("合成人物、画面、字幕与音轨")
            output = compose_avatar(output_dir, effective, video, Path(p["audio_path"]), p["duration"], cues if draft["input"].get("subtitles", True) else [], storyboard=storyboard) if storyboard else compose_avatar(output_dir, effective, video, Path(p["audio_path"]), p["duration"], cues)
        verify(draft,actual_presentation)
        publish_progress("口播画面已合成", True)
        report = {"template_id": actual_presentation['id'], "requested_template_id": selected(draft)['id'], 'base_adapter_template':effective['template_id'], "adapter_version": 1, "avatar_execution":request.get('avatar_execution'), "sources": [{"path": str(video), "sha256": sha(video)}, {"path": p["audio_path"], "sha256": sha(p["audio_path"])}],
                  "presentation":actual_presentation, "requested_presentation":selected(draft),
                  "caption_timing": "Whisper word-level" if cues and asr["provider"] == "local-whisper" else "ASR sentence-level" if cues else "off", "provider_jobs": list(dict.fromkeys(s['job']['id'] for s in [*state['stages'].values(), *[h['stage'] for h in state.get('stage_history', [])]] if s.get('job'))), "human_review": "pending"}
        atomic_private(output_dir / "qa.json", report)
        # This callback runs only after composition's media checks and the QA receipt exist.
        if on_progress: on_progress("成片核验完成，正在登记作品", steps_done + 1, steps_total)
        return {"status": "completed", "stage": "视频已制作完成，可直接播放和下载", "result": {"output_path": str(output), "qa_status": "pending", "notice": composition["notice"], "composition_mode": 'motion' if composition['mode']=='instrument' else 'basic', "effective_template_id": actual_presentation['id'], "presentation":actual_presentation,"requested_presentation":selected(draft), "provider_jobs": report["provider_jobs"]}}
    except ProductionQueueCancelled:
        raise
    except WorkError as exc:
        if exc.code == 'provider_reconciliation':
            return {'status':'ambiguous','stage':str(exc),
                    'error':{'code':exc.code,'message':str(exc),'type':'StudioProviderReceiptUnknown'},
                    'safe_resume_point':'studio_avatar_receipt','retryable':False}
        if exc.code == "provider_pending":
            return {"status": "ambiguous", "stage": str(exc), "error": {"code": "provider_pending", "message": str(exc), "type": "StudioProviderPending"}, "safe_resume_point": "studio_avatar_provider"}
        if exc.code in {"audio_script_mismatch", "audio_check_review", "audio_check_stale", "template_incompatible", "template_mismatch", "budget_exceeded", "local_artifact_missing", "replacement_conflict", "quote_changed"}:
            return {"status": "awaiting_human", "stage": str(exc), "error": {"code": exc.code, "message": str(exc), "type": "StudioInput"}, "safe_resume_point": "studio_avatar_input"}
        if exc.code == "human_required":
            return {"status": "awaiting_human", "stage": str(exc), "error": {"message": str(exc), "type": "StudioMaterialRightsRequired"}, "retryable": False, "safe_resume_point": "studio_avatar_material_rights"}
        return {"status": "failed", "stage": str(exc), "error": {"code": exc.code, "message": str(exc), "type": "StudioAvatar", "retryable": exc.code == "unavailable", "safe_resume_point": "studio_avatar"}, "retryable": exc.code == "unavailable", "safe_resume_point": "studio_avatar"}
    except Exception as exc:
        from backlot.studio_failure import outcome
        return outcome(output_dir, current_stage, exc)
