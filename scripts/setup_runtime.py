"""Install an isolated runtime. Setup downloads public dependencies, never chat data."""
import argparse
import hashlib
import json
import pathlib
import shutil
import struct
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def download_model(destination):
    manifest = json.loads((ROOT/'assets/model-manifest.json').read_text(encoding='utf-8'))
    destination.mkdir()
    for asset in manifest['files']:
        name = asset['file']
        if pathlib.Path(name).name != name:
            raise ValueError('invalid model manifest filename')
        file = destination/name
        part = destination/(name+'.part')
        url = 'https://huggingface.co/'+manifest['repo']+'/resolve/'+manifest['revision']+'/'+name
        with urllib.request.urlopen(url,timeout=60) as response,part.open('xb') as stream:
            shutil.copyfileobj(response,stream,1024*1024)
        with part.open('rb') as stream:
            digest = hashlib.file_digest(stream,'sha256').hexdigest()
        if digest != asset['sha256'] or part.stat().st_size != asset['bytes']:
            raise RuntimeError('model asset integrity check failed: '+name)
        part.replace(file)
    shutil.copy2(ROOT/'assets/model-manifest.json',destination/'asset_manifest.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-dir',type=pathlib.Path,required=True)
    parser.add_argument('--dry-run',action='store_true')
    args = parser.parse_args()
    target = args.install_dir.expanduser().resolve()
    if sys.platform != 'win32' or struct.calcsize('P') != 8 or sys.version_info[:2] != (3,12):
        parser.error('Use 64-bit Python 3.12 on Windows for this validated runtime.')
    if target.exists():
        parser.error('Install directory already exists; refusing to overwrite an existing runtime.')
    template = ROOT/'assets/mcp-runtime'
    digest = hashlib.sha256((template/'vendor/db.py').read_bytes()).hexdigest()
    if digest != '9d4eba69e868dea8000d8acdbaed723149cf8732c52e097f23fb3b07fa5ddc55':
        raise RuntimeError('reviewed reader digest mismatch')
    plan = {'install_dir':str(target),'python':sys.executable,'model_download_bytes':486212372,
            'account_configured':False,'changes_existing_mcp':False}
    if args.dry_run:
        print(json.dumps(plan,ensure_ascii=True,indent=2));return
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(template,target)
    subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check',
        '--only-binary=:all:','--no-compile','--target',str(target/'lib'),
        '-r',str(target/'requirements.lock.txt')],check=True)
    lock = json.loads((ROOT/'assets/asr_requirements.lock.json').read_text(encoding='utf-8'))
    requirements = target/'asr_requirements.lock.txt'
    requirements.write_text('\n'.join(d['name']+'=='+d['version'] for d in lock)+'\n',encoding='utf-8')
    subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check',
        '--only-binary=:all:','--no-compile','--target',str(target/'asr_lib'),
        '-r',str(requirements)],check=True)
    download_model(target/'asr_model')
    print(json.dumps(dict(plan,installed=True),ensure_ascii=True))
    print('Next: configure_account.py with an explicitly selected local account. Keep this install directory private.')


if __name__ == '__main__':
    main()
