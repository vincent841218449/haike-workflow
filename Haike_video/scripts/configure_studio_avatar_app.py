"""Enable/check the local studio's frozen RunningHub AI-app profile; no generation."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backlot.studio import Studio,atomic_private
from backlot.studio_avatar_app import configuration,public_status


def main():
    parser=argparse.ArgumentParser(description='配置4188本地数字人应用，不提交生成或部署服务')
    parser.add_argument('--enable',action='store_true')
    parser.add_argument('--billing',choices=['provider_default','rh_coins'],help='RH币使用单独的RUNNINGHUB_COINS_API_KEY，原密钥保留')
    args=parser.parse_args()
    studio=Studio(Path(__file__).resolve().parents[1]/'projects')
    config=configuration(studio)
    path=studio.private/'haike-api/avatar.local.json'
    options=json.loads(path.read_text()) if path.is_file() else {}
    if args.enable or args.billing:
        if args.billing:
            from backlot.ai_text import _read_env_file,_effective_value
            from tools.avatar.runninghub_ai_app import RunningHubAIAppClient
            _,values=_read_env_file(studio.projects_root.parent/'.env.secrets.local')
            key=_effective_value('RUNNINGHUB_COINS_API_KEY' if args.billing=='rh_coins' else 'RUNNINGHUB_API_KEY',values)
            if not key:parser.error('请先在忽略的.env.secrets.local配置对应RunningHub密钥')
            with RunningHubAIAppClient(key,config['profile']) as client:client.ensure_billing_mode(args.billing)
            options['billing_mode']=args.billing
        elif not config['key']:parser.error('请先在忽略的.env.secrets.local配置对应RunningHub密钥')
        if args.enable: options['enabled']=True
        options['profile']=config['profile']['profile']
        atomic_private(path,options)
    print(json.dumps(public_status(studio),ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
