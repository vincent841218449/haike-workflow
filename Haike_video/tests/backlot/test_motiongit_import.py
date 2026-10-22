import io
import json
import zipfile

import pytest
from scripts import import_motiongit_template as importer


def package(tmp_path, duplicate=False):
    path=tmp_path/'sample.motion'
    files={'00-START-HERE.md':'start','README.md':'readme','assistant/guide.json':'{}',
           'assistant/BUILD.json':json.dumps({'helperVersion':'1.0.0-rc.17'}),
           'assistant/THIRD-PARTY-NOTICES.txt':'license','assistant/motion.mjs':'untrusted-helper'}
    with zipfile.ZipFile(path,'w') as archive:
        for name,value in files.items():archive.writestr(name,value)
        archive.writestr('personal/private.json','private envelope must stay packed')
        if duplicate:
            with pytest.warns(UserWarning):archive.writestr('assistant/motion.mjs','second helper')
    return path


def test_modified_helper_cannot_execute_and_personal_envelope_is_not_extracted(tmp_path,monkeypatch):
    source=package(tmp_path);root=tmp_path/'imports'
    class Official:
        def open(self,*args,**kwargs):return io.BytesIO(json.dumps({'sha256':'not-the-helper','bytes':16}).encode())
    monkeypatch.setattr(importer.urllib.request,'build_opener',lambda *args:Official())
    monkeypatch.setattr(importer.subprocess,'run',lambda *a,**k:pytest.fail('unverified helper executed'))
    with pytest.raises(ValueError,match='官方校验不一致'):
        importer.import_package(source,root,tmp_path/'registry.json')
    assert not list(root.rglob('private.json'))
    assert not (tmp_path/'registry.json').exists()


def test_symlink_source_and_duplicate_tools_are_rejected_before_network(tmp_path,monkeypatch):
    source=package(tmp_path,duplicate=True);link=tmp_path/'link.motion';link.symlink_to(source)
    monkeypatch.setattr(importer.urllib.request,'build_opener',lambda *args:pytest.fail('network must not run'))
    with pytest.raises(ValueError,match='真实官方'):
        importer.import_package(link,tmp_path/'imports',tmp_path/'registry.json')
    with pytest.raises(ValueError,match='重名'):
        importer.import_package(source,tmp_path/'imports',tmp_path/'registry.json')


def test_existing_linked_import_directory_is_not_written(tmp_path):
    source=package(tmp_path);root=tmp_path/'imports';root.mkdir()
    elsewhere=tmp_path/'elsewhere';elsewhere.mkdir()
    (root/importer.sha(source)[:20]).symlink_to(elsewhere,target_is_directory=True)
    with pytest.raises(ValueError,match='目录不能是链接'):
        importer.import_package(source,root,tmp_path/'registry.json')
    assert list(elsewhere.iterdir())==[]
