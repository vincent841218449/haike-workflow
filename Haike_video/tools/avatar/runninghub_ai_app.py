"""Official V2 AI-app transport. This is not the legacy ComfyUI create API."""
from __future__ import annotations

from pathlib import Path

import requests

from tools.avatar.runninghub_avatar import RunningHubAvatarError, billing_evidence, _safe_failure_details


class RunningHubAIAppClient:
    def __init__(self, api_key, profile, session=None):
        self.key, self.profile = api_key, profile
        self.session = session or requests.Session()
        self.session.trust_env = False

    def __enter__(self): return self

    def __exit__(self, *args): self.session.close()

    def _headers(self):
        return {'Authorization': 'Bearer ' + self.key}

    def _json(self, response):
        try:value = response.json()
        except ValueError:
            if response.status_code in {400,401,403,404,422,429}:
                return {'status':'FAILED','errorCode':str(response.status_code),'errorMessage':'数字人服务拒绝请求，请核对应用、密钥权限及可用额度'}
            raise RunningHubAvatarError('数字人服务响应不确定，请查询原请求') from None
        if not isinstance(value, dict): raise RunningHubAvatarError('数字人服务返回格式异常')
        if response.status_code in {400, 401, 403, 404, 422, 429}:
            return {'status':'FAILED', 'errorCode':str(response.status_code), 'errorMessage':'数字人服务拒绝请求，请核对应用、密钥权限及可用额度'}
        if not response.ok: raise RunningHubAvatarError('数字人服务响应不确定，请查询原请求')
        data = value.get('data')
        body = data if isinstance(data, dict) else value
        code = value.get('code')
        if code not in (None, 0, '0', 200, '200', 'SUCCESS', 'success'):
            return {'status':'FAILED', 'errorCode':str(code), 'errorMessage':'数字人服务拒绝请求，请核对应用、密钥权限及可用额度'}
        return body

    def upload(self, path):
        path = Path(path)
        if not path.is_file() or path.stat().st_size > 30 * 1024 * 1024:
            raise RunningHubAvatarError('数字人输入文件不存在或超过30MB')
        with path.open('rb') as source:
            response = self.session.post(self.profile['base_url'] + '/openapi/v2/media/upload/binary',
                headers=self._headers(), files={'file':(path.name,source)}, timeout=(15,180), allow_redirects=False)
        value = self._json(response)
        filename = value.get('fileName')
        if not isinstance(filename, str) or not filename: raise RunningHubAvatarError('数字人输入上传未完成；未提交生成请求')
        return filename

    def submit(self, image, audio):
        p = self.profile
        values = {'image':image, 'audio':audio, 'long_edge':str(p['long_edge']),
                  'prompt':p['prompt'], 'shake':p['shake'], 'zoom':p['zoom']}
        body = {'nodeInfoList':[{'nodeId':node, 'fieldName':field, 'fieldValue':str(values[name])}
                                for name,(node,field) in p['nodes'].items()],
                'instanceType':p['instance_type'], 'usePersonalQueue':False}
        response = self.session.post(p['base_url'] + p['submit_path'], headers=self._headers(),
            json=body, timeout=(15,180), allow_redirects=False)
        value = self._json(response)
        # Both current flat V2 and older enveloped responses are supported.
        return {'task_id':str(value.get('taskId') or ''), 'status':str(value.get('status') or value.get('taskStatus') or 'RUNNING').upper(),
                'error_code':value.get('errorCode'), 'message':value.get('errorMessage')}

    def poll(self, task_id):
        response = self.session.post(self.profile['base_url'] + self.profile['query_path'],
            headers=self._headers(), json={'taskId':task_id}, timeout=(15,60), allow_redirects=False)
        if not response.ok: raise RunningHubAvatarError('原数字人任务查询暂时不可用；不会重提生成')
        value = self._json(response)
        if str(value.get('taskId') or '') != task_id:
            raise RunningHubAvatarError('数字人查询未返回原任务回执，请继续查询原编号')
        state = str(value.get('status') or value.get('taskStatus') or 'RUNNING').upper()
        results = value.get('results') or []
        videos = [v for v in results if isinstance(v,dict) and isinstance(v.get('url'),str)
                  and (str(v.get('outputType','')).lower() in {'mp4','video'} or v['url'].split('?')[0].lower().endswith('.mp4'))]
        return {'status':state, 'task_id':str(value.get('taskId') or task_id), 'videos':videos,
                'error_code':value.get('errorCode'), 'message':value.get('errorMessage'),
                'failure_details':_safe_failure_details(value),
                'billing':billing_evidence(value)}
