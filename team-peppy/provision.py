#!/usr/bin/env python3
"""Run on the Huly host as root. All secrets are resolved and written locally, never printed.

Creates only the selected workspace bot and isolated runtime. Does not modify the existing Superagent.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
import yaml

ROOT = '1749089e-22e6-48de-af4e-165e18fbd2f9'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--directory', default='/opt/team-peppy')
    args = parser.parse_args()
    root = Path(args.directory)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    config = root / 'config'
    config.mkdir(mode=0o700, exist_ok=True)
    containers = json.loads(subprocess.check_output(['docker', 'inspect', 'huly-account-1', 'huly-transactor-1']))
    env = dict(e.split('=', 1) for e in containers[0]['Config']['Env'])
    secret = env.get('SERVER_SECRET') or env['SECRET']
    ip = lambda c: next(iter(c['NetworkSettings']['Networks'].values()))['IPAddress']
    accounts = 'http://' + ip(containers[0]) + ':3000/'
    transactor = 'http://' + ip(containers[1]) + ':3333'

    def jwt(account, workspace=None, extra=None):
        b64 = lambda v: base64.urlsafe_b64encode(v).rstrip(b'=').decode()
        payload = dict(account=account)
        if workspace:
            payload['workspace'] = workspace
        if extra:
            payload['extra'] = extra
        value = b64(b'{"alg":"HS256","typ":"JWT"}') + '.' + b64(json.dumps(payload).encode())
        return value + '.' + b64(hmac.new(secret.encode(), value.encode(), hashlib.sha256).digest())

    def request(url, token, data=None):
        req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.load(response)
        if isinstance(result, dict) and result.get('error'):
            raise RuntimeError('Huly refused operation: ' + str(result['error'].get('code', 'unknown')))
        return result

    def rpc(method, params, token=None):
        return request(accounts, token or jwt(ROOT, extra={'service': 'tool'}), {'method': method, 'params': params}).get('result')

    workspaces = rpc('listWorkspaces', {})
    matches = [w for w in workspaces if w.get('url') == args.workspace or w.get('uuid') == args.workspace]
    if len(matches) != 1:
        raise RuntimeError('Select exactly one existing workspace URL or UUID')
    ws = matches[0]
    wid = ws['uuid']
    admin = jwt(ROOT, wid, {'service': 'tool'})

    def find(cls, query, token=None):
        params = urllib.parse.urlencode({'class': cls, 'query': json.dumps(query), 'options': '{"limit":1000}'})
        rows = request(transactor + '/api/v1/find-all/' + wid + '?' + params, token or admin)
        return rows['value'] if isinstance(rows, dict) and rows.get('dataType') == 'TotalArray' else rows

    def tx(cls, docid, attributes, objectclass='contact:class:Person', space='contact:space:Contacts', **extra):
        data = dict(_id=uuid.uuid4().hex, _class=cls, space='core:space:Tx', objectId=docid,
                    objectClass=objectclass, objectSpace=space, modifiedBy='core:account:System', modifiedOn=int(time.time()*1000), attributes=attributes)
        data.update(extra)
        return request(transactor + '/api/v1/tx/' + wid, admin, data)

    binding_path = config / 'binding.json'
    binding = json.loads(binding_path.read_text()) if binding_path.exists() else {}
    if binding and binding['workspace'] != wid:
        raise RuntimeError('Existing runtime belongs to a different workspace')
    email = 'team-peppy-' + ws['url'] + '@pepper.invalid'
    if not binding:
        person = rpc('findPersonBySocialKey', {'socialString': 'email:' + email})
        if person is None:
            password = secrets.token_urlsafe(48)
            account = rpc('signUp', {'email': email, 'password': password, 'firstName': 'Team', 'lastName': 'Peppy'})['account']
            (config / 'bot-password').write_text(password)
            os.chmod(config / 'bot-password', 0o600)
        else:
            account = person
        # Provisioning uses the host's existing privileged route only here. Runtime receives a normal bot token.
        try:
            rpc('confirm', {}, jwt(account, extra={'service': 'aibot', 'confirmEmail': email}))
        except RuntimeError as error:
            if 'SocialIdAlreadyConfirmed' not in str(error):
                raise
        rpc('assignWorkspace', {'email': email, 'workspaceUuid': wid, 'role': 'USER'})
        bot_token = jwt(account, wid)
        info = request(transactor + '/api/v1/account/' + wid, bot_token)
        social = info['primarySocialId']
        person_id = 'team-peppy-' + wid
        if not find('contact:class:Person', {'_id': person_id}):
            tx('core:class:TxCreateDoc', person_id, dict(personUuid=account, name='Team Peppy', city='', avatarType='color'))
        identities = rpc('getSocialIds', {'includeDeleted': False}, jwt(account))
        for identity in identities:
            if find('contact:class:SocialIdentity', {'_id': identity['_id']}):
                continue
            attrs = dict(attachedTo=person_id, attachedToClass='contact:class:Person', collection='socialIds',
                         type=identity['type'], value=identity['value'], key=identity['type']+':'+identity['value'],
                         verifiedOn=identity.get('verifiedOn', int(time.time()*1000)), isDeleted=False)
            tx('core:class:TxCreateDoc', identity['_id'], attrs, objectclass='contact:class:SocialIdentity',
               attachedTo=person_id, attachedToClass='contact:class:Person', collection='socialIds')
        tx('core:class:TxMixin', person_id, {'active': True, 'role': 'USER'}, mixin='contact:mixin:Employee')
        binding = dict(workspace=wid, workspaceUrl=ws['url'], botAccount=account, botSocial=social, botPerson=person_id)
        binding_path.write_text(json.dumps(binding))
        os.chmod(binding_path, 0o600)
    bot_token = jwt(binding['botAccount'], wid)
    token_path = config / 'huly-token'
    token_path.write_text(bot_token)
    os.chmod(token_path, 0o400)
    os.chown(token_path, 1000, 1000)
    people = find('contact:class:Person', {})
    socials = find('contact:class:SocialIdentity', {})
    allowed = [{'id': s['_id']} for s in socials if s.get('attachedTo') != binding['botPerson'] and not s.get('isDeleted')]
    operators = [p['personUuid'] for p in people if p.get('name') == 'Minzhang Li']
    if not operators:
        raise RuntimeError('No confirmed deployment owner found; configure operators explicitly')
    channels = find('chunter:class:Channel', {'private': False, 'archived': False})
    channel_ids = [c['_id'] for c in channels]
    for channel in channels:
        if binding['botAccount'] not in channel.get('members', []):
            update = dict(_id=uuid.uuid4().hex, _class='core:class:TxUpdateDoc', space='core:space:Tx',
                          objectId=channel['_id'], objectClass=channel['_class'], objectSpace=channel['space'],
                          modifiedBy='core:account:System', modifiedOn=int(time.time()*1000), operations={'$push': {'members': binding['botAccount']}})
            request(transactor+'/api/v1/tx/'+wid, admin, update)
    runtime = root / 'runtime'
    old = Path('/var/lib/docker/volumes/pop-super-agent_runtime/_data')
    if not (runtime / 'profiles/superagent/package.json').exists():
        runtime.mkdir(mode=0o700, exist_ok=True)
        shutil.copytree(old/'profiles/superagent', runtime/'profiles/superagent', symlinks=True)
        if (old/'.env').exists():
            lines = [line for line in (old/'.env').read_text().splitlines() if re.match(r'^(PEPPER_|DEEPSEEK_|OPENAI_|ANTHROPIC_)', line)]
            (runtime/'.env').write_text('\n'.join(lines)+'\n')
        patch = runtime/'profiles/superagent/cordis.patch.yml'
        text = patch.read_text().replace('/home/node/.dsh/state/superagent', '/home/node/.dsh/state/team-peppy')
        text = re.sub(r'(- id: dsh-superagent-feishu\s+disabled:)\s*false', r'\1 true', text)
        text += '\n- id: dsh-superagent-huly\n  disabled: false\n'
        patch.write_text(text)
        subprocess.run(['chown', '-R', '1000:1000', str(runtime)], check=True)
    workspace = root/'workspace'
    workspace.mkdir(mode=0o700, exist_ok=True)
    os.chown(workspace, 1000, 1000)
    # Copy only model API-key references needed by this profile. Browser auth and DeepSeek account records stay separate.
    required_refs = re.findall(r'^\s*apiKeyEnv:\s*[\'"]?([A-Z0-9_]+)', (runtime/'profiles/superagent/cordis.patch.yml').read_text(), re.M)
    original_credentials = yaml.safe_load((old/'.credentials.yaml').read_text())
    destination = runtime/'.credentials.yaml'
    credentials = yaml.safe_load(destination.read_text()) if destination.exists() else {'version': original_credentials['version'], 'records': {}, 'refs': {}}
    for name in required_refs:
        if name not in original_credentials.get('refs', {}):
            raise RuntimeError('The configured model API-key reference is unavailable: '+name)
        credentials.setdefault('refs', {}).setdefault(name, original_credentials['refs'][name])
    destination.write_text(yaml.safe_dump(credentials, sort_keys=False))
    os.chmod(destination, 0o600)
    os.chown(destination, 1000, 1000)
    variables = dict(DSH_SUPERAGENT_HULY_ONLY='1', HULY_WORKSPACE_ID=wid, HULY_WORKSPACE_URL=ws['url'], HULY_ORIGIN='https://superagent-vps.tail0ac8b2.ts.net',
                     HULY_TRANSACTOR_URL='http://transactor:3333', HULY_TOKEN_FILE='/run/secrets/huly-token',
                     HULY_BOT_PERSON=binding['botPerson'], HULY_BOT_SOCIAL=binding['botSocial'], HULY_BOT_ACCOUNT=binding['botAccount'],
                     HULY_CHANNELS=json.dumps(channel_ids), HULY_OPERATORS=json.dumps(operators))
    (config/'runtime.env').write_text('\n'.join(k+'='+v for k,v in variables.items())+'\n')
    os.chmod(config/'runtime.env', 0o600)
    old_settings = json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:3082/orchestrator/api/settings', headers={'x-orchestrator-request':'1'})))
    github = {'enabled': False, 'config': {'repository': '', 'cli': ''}}
    native = dict(github=github, eval=old_settings['blocks']['eval']['value'], executor=old_settings['blocks']['executor']['value'], allowed=allowed)
    native['executor'].update(directory='/workspace/tickets', prepare='', maxWorkers=2)
    (config/'native-settings.json').write_text(json.dumps(native))
    os.chmod(config/'native-settings.json', 0o600)
    print(json.dumps({'workspace': ws['name'], 'workspaceId': wid, 'channels': [c['name'] for c in channels], 'botReady': True, 'runtimePrepared': True}))


if __name__ == '__main__':
    main()
