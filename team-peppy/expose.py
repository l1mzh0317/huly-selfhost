#!/usr/bin/env python3
"""Configure same-origin Team Peppy routes in Huly's nginx, validating before reload."""
import json
from pathlib import Path
import re
import subprocess
import time

BEGIN_MARKER = '    # BEGIN TEAM PEPPY\n'
END_MARKER = '    # END TEAM PEPPY\n'
LOCATION_ANCHOR = '    location / {'
UUID_RE = re.compile(
    r'\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z'
)
INSTANCES_PATH_REGEX = (
    r'^/files/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
    r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/team-peppy(/api/instances(?:/[a-z-]+)?)$'
)


def build_route(workspace: str) -> str:
    """Build the managed nginx route block for PT and multi-workspace Instances API."""
    if not isinstance(workspace, str) or not UUID_RE.fullmatch(workspace):
        raise ValueError(f'Invalid workspace UUID: {workspace!r}')
    return (
        f'    # BEGIN TEAM PEPPY\n'
        f'    location = /team-peppy {{ return 302 /files/{workspace}/team-peppy/; }}\n'
        f'    location = /team-peppy/ {{ return 302 /files/{workspace}/team-peppy/; }}\n'
        f'    location ^~ /files/{workspace}/team-peppy/ {{\n'
        f'        resolver 127.0.0.11 valid=10s ipv6=off;\n'
        f'        set $team_peppy http://team-peppy-app-1:13082;\n'
        f'        rewrite ^/files/{workspace}/team-peppy/(.*)$ /team-peppy/$1 break;\n'
        f'        proxy_pass $team_peppy;\n'
        f'        proxy_http_version 1.1;\n'
        f'        proxy_set_header Host 127.0.0.1:3082;\n'
        f'        proxy_set_header Connection "";\n'
        f'        proxy_buffering off;\n'
        f'        proxy_read_timeout 1h;\n'
        f'    }}\n'
        f'    location ~ "{INSTANCES_PATH_REGEX}" {{\n'
        f'        resolver 127.0.0.11 valid=10s ipv6=off;\n'
        f'        set $team_peppy http://team-peppy-app-1:13082;\n'
        f'        rewrite "{INSTANCES_PATH_REGEX}" /team-peppy/workspaces/$1$2 break;\n'
        f'        proxy_pass $team_peppy;\n'
        f'        proxy_http_version 1.1;\n'
        f'        proxy_set_header Host 127.0.0.1:3082;\n'
        f'        proxy_set_header Connection "";\n'
        f'        proxy_buffering off;\n'
        f'        proxy_read_timeout 1h;\n'
        f'    }}\n'
        f'    # END TEAM PEPPY\n'
    )


def update_nginx_config(text: str, workspace: str) -> str:
    """Insert or idempotently replace the Team Peppy block before `location / {`."""
    route = build_route(workspace)
    if BEGIN_MARKER in text:
        left, tail = text.split(BEGIN_MARKER, 1)
        if END_MARKER not in tail:
            raise ValueError('Found BEGIN TEAM PEPPY marker without matching END TEAM PEPPY marker')
        after_end = tail.split(END_MARKER, 1)[1]
        if after_end.startswith('\n'):
            after_end = after_end[1:]
        text = left + after_end
    index = text.index(LOCATION_ANCHOR)
    return text[:index] + route + '\n' + text[index:]


def main() -> None:
    binding = json.loads(Path('/opt/team-peppy/config/binding.json').read_text())
    workspace = binding['workspace']
    path = Path('/opt/huly/.huly.nginx')
    before = path.read_text()
    updated = update_nginx_config(before, workspace)
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


if __name__ == '__main__':
    main()
