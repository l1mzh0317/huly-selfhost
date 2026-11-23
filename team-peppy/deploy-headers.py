#!/usr/bin/env python3
"""Deploy the paired, verified frontend and DSH images; preserve Compose tags and rollback inputs."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request
import yaml

parser = argparse.ArgumentParser()
parser.add_argument('--frontend', type=Path, required=True)
parser.add_argument('--source', required=True)
parser.add_argument('--dsh-version', required=True)
args = parser.parse_args()
assert re.fullmatch(r'[a-f0-9]{40}', args.source)
assert re.fullmatch(r'[A-Za-z0-9_.-]+', args.dsh_version)
assert (args.frontend/'dist/index.html').is_file()
assert any(b'peppy-message-status' in p.read_bytes() for p in (args.frontend/'dist').rglob('*.js'))

def run(command, cwd=None, env=None):
    subprocess.run(command, cwd=cwd, env=env, check=True)

def inspect(name):
    return json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]

def native():
    req = urllib.request.Request('http://127.0.0.1:3083/orchestrator/api/state', headers={'Host':'127.0.0.1:3082','x-orchestrator-request':'1'})
    with urllib.request.urlopen(req,timeout=10) as res: return json.load(res)

root = Path('/opt/team-peppy')
huly = Path('/opt/huly')
old_front, old_dsh, previous = inspect('huly-front-1'), inspect('team-peppy-app-1'), native()
base = old_front['Config']['Image']
user = old_front['Config'].get('User') or 'root'
assert re.fullmatch(r'[\w./:@-]+', base) and re.fullmatch(r'[\w:-]+', user)
image = 'huly-front-local:0.7.426-peppy-'+args.source[:8]
(args.frontend/'Dockerfile').write_text(f'FROM {base}\nUSER root\nCOPY dist/ /app/dist/\nUSER {user}\n')
run(['docker','build','-t',image,'--label','org.opencontainers.image.revision='+args.source,str(args.frontend)])
config = huly/'compose.override.yaml'
original = config.read_text()
# Compose uses !reset. Update only this scalar's source span; never deserialize and re-dump the document.
def field(node, key): return next((v for k,v in node.value if k.value==key),None)
image_node = field(field(field(yaml.compose(original),'services'),'front'),'image')
assert image_node is not None
updated = original[:image_node.start_mark.index]+json.dumps(image)+original[image_node.end_mark.index:]
backup = root/'backups'/('message-headers-'+str(int(time.time())))
backup.mkdir(parents=True,mode=0o700); backup.chmod(0o700)
(backup/'huly-compose.override.yaml').write_text(original); (backup/'huly-compose.override.yaml').chmod(0o600)
version = root/'.env'
original_env = version.read_text() if version.exists() else ''
(backup/'team-peppy.env').write_text(original_env); (backup/'team-peppy.env').chmod(0o600)
(backup/'images.json').write_text(json.dumps({'front':old_front['Config']['Image'],'dsh':old_dsh['Config']['Image'],'masterId':previous['masterId']}))

def set_version(value):
    text = re.sub(r'^TEAM_PEPPY_VERSION=.*$', 'TEAM_PEPPY_VERSION='+value, original_env, flags=re.M)
    if not re.search(r'^TEAM_PEPPY_VERSION=',text,re.M): text += '\nTEAM_PEPPY_VERSION='+value+'\n'
    version.write_text(text);version.chmod(0o600)

front_command = ['docker','compose','-f','compose.yml','-f','compose.override.yaml']
try:
    run(['docker','compose','stop','-t','120','app'],root)
    shutil.copytree(root/'runtime',backup/'runtime',symlinks=True)
    set_version(args.dsh_version)
    config.write_text(updated)
    run(front_command+['config','--quiet'],huly)
    run(['docker','compose','up','-d','--no-deps','app'],root)
    for _ in range(60):
        try:
            state=native()
            if state['health']['runtime']['state']=='ready': break
        except Exception: pass
        time.sleep(1)
    else: raise RuntimeError('New DSH instance did not become ready')
    assert state['masterId']==previous['masterId'], 'Unexpected orchestration namespace change'
    run(front_command+['up','-d','--no-deps','front'],huly)
    front=inspect('huly-front-1')
    address=next(iter(front['NetworkSettings']['Networks'].values()))['IPAddress']
    for _ in range(30):
        try:
            with urllib.request.urlopen('http://'+address+':8080/',timeout=5) as res:
                if res.status==200: break
        except Exception: pass
        time.sleep(1)
    else: raise RuntimeError('Frontend did not become ready')
    run(['docker','exec','huly-nginx-1','nginx','-t'])
    run(['docker','exec','huly-nginx-1','nginx','-s','reload'])
except Exception:
    config.write_text(original)
    old_tag=old_dsh['Config']['Image'].split(':')[-1]
    set_version(old_tag)
    run(['docker','compose','up','-d','--no-deps','app'],root)
    run(front_command+['up','-d','--no-deps','front'],huly)
    run(['docker','exec','huly-nginx-1','nginx','-s','reload'])
    raise
print(json.dumps({'frontendImage':image,'dshVersion':args.dsh_version,'source':args.source,'originalMasterPreserved':True,'privateBackup':str(backup)}))
