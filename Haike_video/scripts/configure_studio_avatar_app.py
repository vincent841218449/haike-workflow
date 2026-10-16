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
    args=parser.parse_args()
    studio=Studio(Path(__file__).resolve().parents[1]/'projects')
    config=configuration(studio)
    if args.enable:
        if not config['key']:parser.error('请先在忽略的.env.secrets.local配置RUNNINGHUB_API_KEY')
        atomic_private(studio.private/'haike-api/avatar.local.json',{'enabled':True,'profile':config['profile']['profile']})
    print(json.dumps(public_status(studio),ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
