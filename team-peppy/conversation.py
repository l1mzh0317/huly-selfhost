#!/usr/bin/env python3
"""Upgrade conversation behavior while preserving current allowed members, rules, models and administrator prompts."""
import json
from pathlib import Path
import re
import urllib.request


def api(path, data=None, method=None):
    req = urllib.request.Request('http://127.0.0.1:3083/orchestrator/api/'+path,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={'Host': '127.0.0.1:3082', 'x-orchestrator-request': '1', 'Content-Type': 'application/json'}, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def section(text, name, body):
    start, end = '<!-- '+name+' -->', '<!-- /'+name+' -->'
    text = re.sub(re.escape(start)+r'.*?'+re.escape(end), '', text, flags=re.S).strip()
    return text+'\n\n'+start+'\n'+body.strip()+'\n'+end


settings = api('settings')
current = settings['blocks']['eval']
if current['value']['mode'] != 'auto':
    # Huly's Source only observes threads that have actually invited the bot. Other channel traffic stays outside intake.
    api('settings/eval', {'revision': current['revision'], 'value': {**current['value'], 'mode': 'auto'}}, 'PUT')

prompts = api('prompts')
config = prompts['current']['config']
old = json.dumps(config, sort_keys=True)
config['communication'] = section(config['communication'], 'team-peppy-thread-conversation', '''
Huly Team Peppy conversation contract (specific to this workspace):
Every real typed @Team Peppy mention must receive a substantive answer in its original Huly thread, including discussion-only questions. A received reaction or routing status is not the answer. For quick discussion, use orchestrator_reply purpose=answer with the original trigger_id, then settle the candidate without creating an unnecessary ticket. Do not silently ignore an explicit mention. If a limitation prevents an answer, state it honestly in that thread.
After a thread invites Team Peppy, subsequent human replies in the same thread are context, even without another mention. Read the original thread before interpreting short follow-ups. Unmentioned discussion need not receive a reply: adopt only relevant questions or clearly requested work; remain silent on unrelated talk or thanks. When a worker decides to take up an unmentioned request, call orchestrator_ack for that exact trigger before substantial work, or report its answer with reply_to_trigger_id. Delivering or reading context alone is not taking it up. Never acknowledge merely to quiet a status indicator.
Keep all existing sender, channel, Mandate and human-stop restrictions. A discussion does not authorize implementation. Do not use thread context to expand a task's scope. Channel status, task/session links and received reactions are maintained by the adapter; do not duplicate them in your answer.
''')
parts = {p['key']: p for p in prompts['parts']}
overrides = config.setdefault('overrides', {})
part = overrides.get('runtime/admission', {'text': parts['runtime/admission']['text'], 'base': parts['runtime/admission']['base']})
overrides['runtime/admission'] = {**part, 'text': section(part['text'], 'team-peppy-thread-admission', '''
Huly activated-thread exception for conversational answers: for an allowed member's relevant unmentioned question inside a thread that already invited Team Peppy (meta.observedThread=true), you may answer that question directly through orchestrator_reply purpose=answer using its trigger_id, then ignore the candidate as discussion. No new implementation authority is granted by answering. Unrelated conversation and acknowledgements such as thanks should be ignored silently. Starting or extending execution still requires the native Policy, enabled rules, concrete intent, settled scope and existing Mandate checks above. Never apply this exception to messages from other Sources or outside an invited Huly thread.
''')}
if json.dumps(config, sort_keys=True) != old:
    api('prompts', {'baseRevision': prompts['current']['revision'], 'config': config}, 'PUT')
print(json.dumps({'threadObservation': 'invited-threads-only', 'unmentionedMessages': 'context-until-adopted', 'mentionedMessages': 'answer-required'}))
