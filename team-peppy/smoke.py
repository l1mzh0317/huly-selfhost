#!/usr/bin/env python3
"""Real integration check in a dedicated private PT channel; never impersonates a real member.

Creates a clearly named validator account and exchanges messages only with Team Peppy in that channel.
Secrets stay on the host. Prints only test receipts and identifiers.
"""
import base64
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import subprocess
import time
import urllib.parse
import urllib.request
import urllib.error
import uuid
import sys

ROOT = Path('/opt/team-peppy')
b = json.loads((ROOT/'config/binding.json').read_text())
containers = json.loads(subprocess.check_output(['docker', 'inspect', 'huly-account-1', 'huly-transactor-1']))
env = dict(e.split('=', 1) for e in containers[0]['Config']['Env'])
secret = env.get('SERVER_SECRET') or env['SECRET']
ip = lambda c: next(iter(c['NetworkSettings']['Networks'].values()))['IPAddress']
accounts = 'http://' + ip(containers[0]) + ':3000/'
transactor = 'http://' + ip(containers[1]) + ':3333/api/v1/'
wid = b['workspace']
origin = 'https://superagent-vps.tail0ac8b2.ts.net'


def jwt(account, workspace=None, extra=None):
    payload = dict(account=account, exp=int(time.time())+3600)
    if workspace:
        payload['workspace'] = workspace
    if extra:
        payload['extra'] = extra
    enc = lambda v: base64.urlsafe_b64encode(v).rstrip(b'=').decode()
    value = enc(b'{"alg":"HS256","typ":"JWT"}') + '.' + enc(json.dumps(payload).encode())
    return value + '.' + enc(hmac.new(secret.encode(), value.encode(), hashlib.sha256).digest())


admin = jwt('1749089e-22e6-48de-af4e-165e18fbd2f9', wid, {'service': 'tool'})


def request(url, token=None, data=None, method=None):
    headers = {'Content-Type': 'application/json', 'Origin': origin, 'x-team-peppy-request': '1'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if ':3083/' in url:
        headers.update({'Host': '127.0.0.1:3082', 'x-orchestrator-request': '1'})
        if '/orchestrator/api/' in url:
            headers.pop('Origin')
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.load(response)
    if isinstance(result, dict) and result.get('error'):
        raise RuntimeError(str(result['error']))
    return result


def rpc(method, params, token=admin):
    return request(accounts, token, {'method': method, 'params': params}).get('result')


def find(cls, query, token=admin):
    query = urllib.parse.urlencode({'class': cls, 'query': json.dumps(query), 'options': '{"limit":1000}'})
    rows = request(transactor+'find-all/'+wid+'?'+query, token)
    return rows['value'] if isinstance(rows, dict) else rows


def tx(cls, docid, attrs, token=admin, social='core:account:System', space='core:space:Space', **extra):
    data = dict(_id=uuid.uuid4().hex, _class='core:class:TxCreateDoc', space='core:space:Tx', objectId=docid, objectClass=cls,
                objectSpace=space, modifiedOn=int(time.time()*1000), modifiedBy=social, createdBy=social, attributes=attrs)
    data.update(extra)
    return request(transactor+'tx/'+wid, token, data)


email = 'team-peppy-validator-'+b['workspaceUrl']+'@pepper.invalid'
qa = rpc('findPersonBySocialKey', {'socialString': 'email:'+email})
if not qa:
    qa = rpc('signUp', {'email': email, 'password': secrets.token_urlsafe(48), 'firstName': 'Team Peppy', 'lastName': '接入检查'})['account']
try:
    rpc('confirm', {}, jwt(qa, extra={'service': 'aibot', 'confirmEmail': email}))
except RuntimeError as error:
    if 'SocialIdAlreadyConfirmed' not in str(error):
        raise
rpc('assignWorkspace', {'email': email, 'workspaceUuid': wid, 'role': 'USER'})
token = jwt(qa, wid)
info = request(transactor+'account/'+wid, token)
social = info['primarySocialId']
channel = 'team-peppy-integration-'+wid
owner = '4e57659e-ac29-4940-8270-d5c1532fdd27'
if not find('chunter:class:Channel', {'_id': channel}):
    tx('chunter:class:Channel', channel, {'name': 'Team Peppy 接入验证', 'description': '自动接入检查专用，不向其他团队成员发送消息。',
                                      'private': True, 'archived': False, 'members': [qa, b['botAccount'], owner]})

native_url = 'http://127.0.0.1:3083/orchestrator/api/'
ui_url = 'http://127.0.0.1:3083/team-peppy/api/'


def save(block, value):
    settings = request(native_url+'settings')
    current = next(s for s in settings['sources'] if 'source:'+s['id']==block) if block.startswith('source:') else settings['blocks'][block]
    request(native_url+'settings/'+block, data={'revision': current['revision'], 'value': value}, method='PUT')


settings = request(native_url+'settings')
config = next(s['value'] for s in settings['sources'] if s['id']=='huly')
if channel not in config['config']['channels']:
    config['config']['channels'].append(channel)
    save('source:huly', config)
policy = settings['blocks']['policy']['value']
known = {a['id'] for a in policy['sources']['huly']['allowed']}
policy['sources']['huly']['allowed'] += [{'id': s, 'name': 'Team Peppy 接入检查'} for s in info['socialIds'] if s not in known]
save('policy', policy)
before = {t['id'] for t in request(ui_url+'tasks', token)['items']}
nonce = uuid.uuid4().hex[:8]
marker = 'HULY_DSH_OK_'+nonce
root = 'peppy-smoke-'+nonce
text = '请建立一个名为“连接验证 '+nonce+'”的工单，交给 worker 检查其当前工作目录是否存在。只做这个无副作用检查，不修改文件、不调用外部服务。然后在线程回复 '+marker+'，并保持等待补充，不要结束工单。'
markup = json.dumps({'type': 'doc', 'content': [{'type': 'paragraph', 'content': [
    {'type': 'reference', 'attrs': {'id': b['botPerson'], 'objectclass': 'contact:class:Person', 'label': 'Team Peppy'}}, {'type': 'text', 'text': ' '+text}]}]})
tx('chunter:class:ChatMessage', root, {'message': markup}, token, social, channel,
   attachedTo=channel, attachedToClass='chunter:class:Channel', collection='messages')
print(json.dumps({'phase': 'huly-message-created', 'root': root}), flush=True)
task = None
deadline = time.time()+240
while time.time() < deadline:
    items = request(ui_url+'tasks', token)['items']
    candidates = [t for t in items if t['id'] not in before and root in (t.get('sourceUrl') or '')]
    if candidates and candidates[0]['sessionId']:
        task = candidates[0]
        break
    time.sleep(2)
if not task:
    raise RuntimeError('No worker task appeared for the Huly message')
print(json.dumps({'phase': 'worker-linked', 'task': task['id'], 'sessionId': task['sessionId']}), flush=True)
path = ui_url+'tasks/'+task['id']
takeover = 'SESSION_TAKEOVER_OK_'+nonce
payload = dict(sessionId=task['sessionId'], requestId=str(uuid.uuid4()), text='Dashboard 接手验证：请在原线程回复 '+takeover+'，并继续等待补充。', mode='steer')
receipt = request(path+'/messages', token, payload)
request(path+'/messages', token, payload)
assert receipt['sessionId']==task['sessionId']
print(json.dumps({'phase': 'same-session-input-accepted', 'sessionId': receipt['sessionId']}), flush=True)
deadline = time.time()+240
while time.time() < deadline:
    detail = request(native_url+'tickets/'+task['id'])
    count = sum(takeover in str(i.get('trigger', {}).get('preview', '')) for i in detail['inputs'])
    replies = find('chunter:class:ThreadMessage', {'attachedTo': root}, token)
    returned = any(takeover in str(r.get('message', '')) for r in replies)
    if returned:
        assert count==1, 'The retried Dashboard input must appear exactly once'
        break
    time.sleep(2)
else:
    raise RuntimeError('Worker did not return the takeover result to the original thread')
stream_request = urllib.request.Request(path+'/session', headers={'Host':'127.0.0.1:3082','Authorization':'Bearer '+token})
with urllib.request.urlopen(stream_request, timeout=30) as stream:
    for line in stream:
        if line.startswith(b'data: '):
            snapshot = json.loads(line[6:]); assert snapshot['type']=='snapshot' and snapshot['sessionId']==task['sessionId']; break
for invalid, expected in [(None, 401), (jwt(qa, '0596cd5f-58b8-4fa4-866d-ba3fde08562a'), 403)]:
    try:
        request(ui_url+'tasks', invalid)
        raise AssertionError('Unauthorized query was accepted')
    except urllib.error.HTTPError as error:
        assert error.code==expected
print(json.dumps({'phase':'passed','task':task['id'],'sessionId':task['sessionId'],'root':root,'inputCount':count,'snapshotRecords':len(snapshot['records']),'replyReturned':True}), flush=True)

if '--conversation' in sys.argv:
    def wait_for(check, label, seconds=300):
        until = time.time()+seconds
        while time.time() < until:
            value = check()
            if value:
                return value
            time.sleep(2)
        raise RuntimeError('Conversation check timed out: '+label)

    def reactions(message):
        return find('activity:class:Reaction', {'attachedTo': message, 'createBy': b['botSocial'], 'emoji': '✅'}, token)

    def replies(message):
        return find('chunter:class:ThreadMessage', {'attachedTo': message}, token)

    def has_answer(message, answer):
        return next((r for r in replies(message) if answer in str(r.get('message', ''))), None)

    def send(message, text, mention=False, parent=None):
        content = ([{'type': 'reference', 'attrs': {'id': b['botPerson'], 'objectclass': 'contact:class:Person', 'label': 'Team Peppy'}}] if mention else [])
        content.append({'type': 'text', 'text': ' '+text})
        attrs = {'message': json.dumps({'type': 'doc', 'content': [{'type': 'paragraph', 'content': content}]})}
        if parent:
            attrs.update(objectId=channel, objectClass='chunter:class:Channel')
        tx('chunter:class:ThreadMessage' if parent else 'chunter:class:ChatMessage', message, attrs, token, social, channel,
           attachedTo=parent or channel, attachedToClass='chunter:class:ChatMessage' if parent else 'chunter:class:Channel', collection='replies' if parent else 'messages')

    def badge(message):
        rows = request(ui_url+'message-status?'+urllib.parse.urlencode({'message':message}), token)['items']
        return rows[0] if rows else None

    shown = wait_for(lambda: badge(root), 'message-header status', 30)
    assert shown['taskId']==task['id'] and shown['sessionId']==task['sessionId']
    assert shown['sessionName']==task['title']
    assert not reactions(root), 'Header status must not create an emoji receipt'
    worker_reply = has_answer(root, takeover)
    assert worker_reply and '?task=' not in worker_reply['message'] and 'Worker ·' not in worker_reply['message'], 'Actual worker reply must not append a session footer'
    print(json.dumps({'phase':'message-header-session-binding-verified','noEmojiReceipt':True,'noSessionFooter':True}), flush=True)

    background = 'THREAD_CONTEXT_'+nonce
    background_id = 'peppy-context-'+nonce
    send(background_id, background+'：只是补充背景供你了解，不需要回复，也不需要采取任何行动。', parent=root)
    def context_read():
        current = request(native_url+'tickets/'+task['id'])
        return next((i for i in current['inputs'] if background in str(i.get('trigger',{}).get('preview','')) and i.get('readAt')), None)
    wait_for(context_read, 'unmentioned context reached original worker')
    assert not badge(background_id), 'Context alone must not be marked as adopted'
    print(json.dumps({'phase':'unmentioned-context-read-silently'}), flush=True)

    adopted = 'THREAD_ADOPTED_'+nonce
    adopted_id = 'peppy-adopted-'+nonce
    send(adopted_id, '继续刚才的目录验证，请回答当前工作目录是否存在，并在这个原线程回复 '+adopted+'。只回答该问题，不修改文件；回答后继续等候。', parent=root)
    wait_for(lambda: has_answer(root, adopted), 'unmentioned request answered')
    assert wait_for(lambda: badge(adopted_id), 'adopted message-header status', 30)['sessionId']==task['sessionId']
    assert not reactions(adopted_id)
    print(json.dumps({'phase':'unmentioned-adopted-and-marked'}), flush=True)

    discussion = 'peppy-discussion-'+nonce
    answer = 'DISCUSSION_OK_'+nonce
    send(discussion, '只讨论产品体验，不要创建工单，不要执行工具：等待 AI 回复时，显示已接收状态是否有助于减少焦虑？请用一句话回答，并包含 '+answer+'。', mention=True)
    wait_for(lambda: has_answer(discussion, answer), 'explicit discussion mention must receive an answer')
    assert wait_for(lambda: badge(discussion), 'discussion header receipt', 30)['sessionId'] is None
    assert not reactions(discussion)
    followup = 'DISCUSSION_FOLLOWUP_'+nonce
    followup_id = 'peppy-discussion-followup-'+nonce
    send(followup_id, '接着刚才的产品讨论：除了已接收，你觉得显示哪个状态最有帮助？请用一句话回答，并包含 '+followup+'。仍然只讨论，不要创建工单或执行工具。', parent=discussion)
    wait_for(lambda: has_answer(discussion, followup), 'discussion without another mention must stay in context')
    assert wait_for(lambda: badge(followup_id), 'adopted discussion header receipt', 30)['sessionId'] is None
    all_tasks = request(ui_url+'tasks', token)['items']
    assert not any(discussion in (t.get('sourceUrl') or '') for t in all_tasks), 'Discussion must not allocate an unnecessary worker'
    print(json.dumps({'phase':'conversation-passed','task':task['id'],'sessionId':task['sessionId'],'discussionRoot':discussion,'messageHeaderStatus':True,'noEmojiReceipt':True,'contextOnlySilent':True,'unmentionedAdoptionMarked':True,'discussionAnsweredWithoutWorker':True}), flush=True)
