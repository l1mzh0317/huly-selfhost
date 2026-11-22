#!/usr/bin/env python3
"""Add one workspace-scoped same-origin route, validating nginx before reload."""
import json
from pathlib import Path
import subprocess
import time

binding = json.loads(Path('/opt/team-peppy/config/binding.json').read_text())
workspace = binding['workspace']
path = Path('/opt/huly/.huly.nginx')
text = path.read_text()
start, end = '    # BEGIN TEAM PEPPY\n', '    # END TEAM PEPPY\n'
if start in text:
    left, tail = text.split(start, 1)
    text = left + tail.split(end, 1)[1]
route = '''    # BEGIN TEAM PEPPY
    location = /team-peppy { return 302 /files/WORKSPACE/team-peppy/; }
    location = /team-peppy/ { return 302 /files/WORKSPACE/team-peppy/; }
    location ^~ /files/WORKSPACE/team-peppy/ {
        resolver 127.0.0.11 valid=10s ipv6=off;
        set $team_peppy http://team-peppy-app-1:13082;
        rewrite ^/files/WORKSPACE/team-peppy/(.*)$ /team-peppy/$1 break;
        proxy_pass $team_peppy;
        proxy_http_version 1.1;
        proxy_set_header Host 127.0.0.1:3082;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_read_timeout 1h;
    }
    # END TEAM PEPPY
'''.replace('WORKSPACE', workspace)
index = text.index('    location / {')
updated = text[:index] + route + '\n' + text[index:]
before = path.read_text()
backup = path.with_name(path.name + '.before-team-peppy-' + str(int(time.time())))
backup.write_text(before)
backup.chmod(0o600)
path.write_text(updated)
try:
    subprocess.run(['docker', 'exec', 'huly-nginx-1', 'nginx', '-t'], check=True)
    subprocess.run(['docker', 'exec', 'huly-nginx-1', 'nginx', '-s', 'reload'], check=True)
except Exception:
    path.write_text(before)
    raise
print('Dashboard route ready at /files/' + workspace + '/team-peppy/')
