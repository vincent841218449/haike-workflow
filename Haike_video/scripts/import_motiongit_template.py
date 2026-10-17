"""Import a personally downloaded ADu package through its verified official entry.

No personal envelope is extracted. Imports never enable paid services or mark a
template production-ready. Existing registry entries and frozen jobs stay intact.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request
import zipfile

from backlot.studio import atomic_private
from backlot.work_catalog import sha


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


def import_package(source, root, registry, node='node'):
    source=Path(source)
    if not source.is_file() or source.is_symlink() or not 0<source.stat().st_size<=250*1024*1024:
        raise ValueError('请选择250MB以内的真实官方个人模板包')
    source=source.resolve();root=Path(root).resolve();registry=Path(registry).resolve()
    fingerprint=sha(source);directory=root/fingerprint[:20]
    if directory.is_symlink():raise ValueError('导入目录不能是链接')
    directory.mkdir(parents=True,exist_ok=True,mode=0o700);directory.chmod(0o700)
    package=directory/'original.motion'
    if package.is_symlink():raise ValueError('导入文件不能是链接')
    if package.exists() and sha(package)!=fingerprint:raise ValueError('导入目录已绑定其他模板包')
    if not package.exists():shutil.copy2(source,package)
    package.chmod(0o600)
    names=['00-START-HERE.md','README.md','assistant/guide.json','assistant/BUILD.json','assistant/THIRD-PARTY-NOTICES.txt','assistant/motion.mjs']
    with zipfile.ZipFile(package) as archive:
        for name in names:
            if archive.namelist().count(name)!=1:raise ValueError('模板外层工具缺失或重名')
            info=archive.getinfo(name)
            if info.file_size>2*1024*1024 or (info.external_attr>>16)&0o170000==0o120000:
                raise ValueError('模板外层工具格式无效')
            target=directory/'tools'/name
            if any(p.is_symlink() for p in [target,*target.parents] if p!=root and p.is_relative_to(root)):
                raise ValueError('导入工具不能是链接')
            target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            target.write_bytes(archive.read(name));target.chmod(0o600)
    build=json.loads((directory/'tools/assistant/BUILD.json').read_text())
    version=build['helperVersion']
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-rc\.\d+)?',version):raise ValueError('官方工具版本无效')
    url=f'https://motiongit.com/assets/motion-runtimes/{version}.json'
    metadata=json.load(urllib.request.build_opener(NoRedirect()).open(url,timeout=30))
    helper=directory/'tools/assistant/motion.mjs'
    if sha(helper)!=metadata['sha256'] or helper.stat().st_size!=metadata['bytes']:
        raise ValueError('随包工具与官方校验不一致，未执行模板代码')
    atomic_private(directory/'helper-verification.json',metadata)

    def read(operation,*args):
        result=subprocess.run([node,str(helper),operation,str(package),*map(str,args)],capture_output=True,text=True,timeout=120)
        # Raw output may contain recipient metadata. Keep it private; emit no
        # original stderr, account information, personal URLs or identifiers.
        atomic_private(directory/(operation+'-receipt.json'),{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        if result.returncode:raise ValueError(f'官方{operation}未通过，脱敏提示之外的回执仅保存在本机')
        return json.loads(result.stdout)

    start=read('start')
    if start.get('verified') is not True:raise ValueError('原始模板签名尚未通过')
    guide=start['templateGuide']['content'];identity=start['templateGuide']['deliveryIdentity']
    schema=read('read','params.schema.json')['content']
    public=start['templateGuide']['currentTemplate']
    if public['version']!=identity['templateVersion']:
        raise ValueError('原包签名版本与公开参数合同不一致')
    style='motiongit-'+str(identity['templateId'])+'-v'+public['version'].replace('.','-')
    if not re.fullmatch(r'motiongit-\d+-v[0-9A-Za-z-]+',style):raise ValueError('模板版本身份无效')
    extension=guide.get('extensionLibrary',{})
    capabilities={k:extension[k] for k in ['controls','styleProfiles','transitions'] if k in extension}
    for filename,value in [('guide.json',guide),('schema.json',schema),('capabilities.json',capabilities)]:
        atomic_private(directory/filename,value)
    properties=schema.get('properties',{})
    kind='macro' if 'brief' in properties else 'recipe' if 'segments' in properties else 'unsupported'
    profile=extension.get('styleProfiles',{}).get('defaultProfile','console')
    config={'style':style,'display_name':public['name'],'template_id':public['id'],'version':public['version'],
        'layout':public['layout'],'native_kind':kind,'style_profile':profile,
        'package':str(package),'package_sha256':fingerprint,
        'release_sha256':identity['releaseArchiveSha256'],'node':node,
        'cache':str(directory/'cache-kit'),'native_cache':str(directory/'cache-native'),
        'production_ready':False,'validation_status':'imported-signature-verified'}
    for field,filename in [('helper','tools/assistant/motion.mjs'),('schema','schema.json'),('capabilities','capabilities.json'),('guide','guide.json')]:
        config[field]=str(directory/filename);config[field+'_sha256']=sha(directory/filename)
    entries=json.loads(registry.read_text()) if registry.is_file() else {}
    if style in entries and entries[style].get('package_sha256')!=fingerprint:
        raise ValueError('同一模板版本已经导入另一份个人包，原记录保留')
    if style not in entries:
        entries[style]=config;atomic_private(registry,entries)
    return {'style':style,'name':public['name'],'version':public['version'],'layout':public['layout'],
        'native_kind':kind,'controls':len(capabilities.get('controls',{})),'ready':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='导入官方个人 .motion，不包含生成、在线登记或付费功能')
    parser.add_argument('package');parser.add_argument('--root',required=True);parser.add_argument('--registry',required=True);parser.add_argument('--node',default='node')
    args=parser.parse_args()
    print(json.dumps(import_package(args.package,args.root,args.registry,args.node),ensure_ascii=False))
