"""Experimental Threads polls/video. Remote eligibility and launch remain gated.

Video containers are checkpointed before publishing; an uncertain publish is never
repeated. Processing spans scheduler ticks instead of blocking the Pi.
"""
import datetime as dt
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from buffer_adapter import PublishError, verify_media


def token():
    root=os.environ.get('CREDENTIALS_DIRECTORY')
    if not root:raise PublishError('authorization')
    value=(Path(root)/'THREADS_ACCESS_TOKEN').read_text().strip()
    if not value:raise PublishError('authorization')
    return value


def denied(data):
    # Missing grants (e.g. threads_manage_replies) arrive as OAuth codes, often on HTTP 400.
    error=data.get('error') if isinstance(data,dict) else None
    code=error.get('code') if isinstance(error,dict) else None
    return isinstance(code,int) and (code in (10,190) or 200<=code<300)


def request(method,path,params,access_token):
    # me/replies: the account's own replies, searched to reconcile companion replies.
    if not re.fullmatch(r'(me|[0-9]+)(/threads|/threads_publish|/threads_publishing_limit)?|me/replies',path):raise PublishError('rejected')
    body=urllib.parse.urlencode(params).encode()
    url='https://graph.threads.net/v1.0/'+path
    if method=='GET':url+='?'+body.decode();body=None
    req=urllib.request.Request(url,data=body,method=method,headers={'Authorization':'Bearer '+access_token,'Content-Type':'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req,timeout=30) as response:data=json.load(response)
    except urllib.error.HTTPError as error:
        if error.code==429:raise PublishError('rate_limit',3600) from None
        if error.code in (401,403):raise PublishError('authorization') from None
        if error.code==400:
            try:body=json.loads(error.read(65536))
            except (OSError,ValueError):body={}
            raise PublishError('authorization' if denied(body) else 'rejected') from None
        raise PublishError('uncertain') from None
    except (OSError,ValueError):raise PublishError('uncertain') from None
    if data.get('error'):raise PublishError('authorization' if denied(data) else 'uncertain')
    return data


def caption_matches(post, expected):
    if post.get('text') == expected:
        return True
    # Threads converts the first hashtag to a topic and omits its # in text.
    # Require the API topic field and otherwise byte-for-byte matching text.
    first = re.search(r'(?<!\w)#([A-Za-z0-9_]+)', expected)
    return bool(first and post.get('topic_tag') == first.group(1)
                and post.get('text') == expected[:first.start()] + expected[first.start()+1:])


class ThreadsAdapter:
    def __init__(self,ledger,config,transport=request,token_loader=token,pause_check=lambda:False):
        self.ledger,self.config,self.transport,self.token_loader=ledger,config,transport,token_loader
        self.pause_check=pause_check
        with ledger.db:
            ledger.db.execute('CREATE TABLE IF NOT EXISTS threads_containers(job TEXT PRIMARY KEY, container TEXT NOT NULL, attempted INTEGER NOT NULL DEFAULT 0, post TEXT)')

    def call(self,method,path,params):
        # Direct publishing uses its own conservative request bucket, not Buffer's.
        with self.ledger.db:
            self.ledger.db.execute('CREATE TABLE IF NOT EXISTS threads_calls(at REAL)')
            now=time.time()
            if self.ledger.db.execute('SELECT count(*) FROM threads_calls WHERE at>?',(now-86400,)).fetchone()[0]>=100:
                raise PublishError('budget')
            self.ledger.db.execute('INSERT INTO threads_calls VALUES(?)',(now,))
            self.ledger.db.execute('DELETE FROM threads_calls WHERE at<?',(now-86400,))
        return self.transport(method,path,params,self.token_loader())

    def identity(self,job):
        profile=self.call('GET','me',{'fields':'id,username'})
        c=self.config['channels']['threads']
        if str(profile['id'])!=job['account'] or profile['username'].lower()!=c['profileUrl'].rstrip('/').split('@')[-1].lower():
            raise PublishError('authorization')

    def quota(self):
        data=self.call('GET','me/threads_publishing_limit',{'fields':'quota_usage,config'})
        try:
            limit=data['data'][0]
            usage,total=limit['quota_usage'],limit['config']['quota_total']
            if not isinstance(usage,int) or not isinstance(total,int) or usage<0 or total<1:
                raise ValueError()
        except (KeyError,IndexError,TypeError,ValueError):raise PublishError('rejected') from None
        if usage>=total:raise PublishError('rate_limit',3600)

    def publish(self,job,payload):
        self.identity(job)
        if payload.get('companion'):return self.reply(job,payload)
        options=payload.get('nativePoll')
        if self.config['channels']['threads'].get('threadsFormat')=='video':
            if options or len(payload['caption'])>500:raise PublishError('rejected')
            verify_media(payload,self.config)
            data=self.call('POST','me/threads',{'media_type':'VIDEO','video_url':payload['media']['url'],'text':payload['caption']})
            container=str(data['id'])
            if not container.isdecimal():raise PublishError('uncertain')
            with self.ledger.db:
                self.ledger.db.execute('INSERT INTO threads_containers(job,container) VALUES(?,?)',(job['id'],container))
            return {'remoteId':'container:'+container}
        if not options or not 2<=len(options)<=4 or any(not v or len(v.encode())>25 for v in options):
            raise PublishError('rejected')
        if len(payload['caption'])>500:raise PublishError('rejected')
        self.quota()
        if self.pause_check():raise PublishError('rate_limit',300)
        params={'media_type':'TEXT','text':payload['caption'],'auto_publish_text':'true',
                'poll_attachment':json.dumps({f'option_{chr(97+i)}':value for i,value in enumerate(options)})}
        data=self.call('POST','me/threads',params)
        return {'remoteId':str(data['id'])}

    def reply(self,job,payload):
        # Text-only reply; native poll replies stay unverified, so a poll companion is plain text.
        parent=str((payload.get('parent') or {}).get('remoteId') or '')
        if payload.get('kind') not in ('comment','answer','poll') or not payload.get('caption') or len(payload['caption'])>500 or not parent.isdecimal():
            raise PublishError('rejected')
        if self.ledger.db.execute('SELECT 1 FROM threads_containers WHERE job=?',(job['id'],)).fetchone():raise PublishError('uncertain')
        self.quota()
        if self.pause_check():raise PublishError('rate_limit',300)
        with self.ledger.db:
            self.ledger.db.execute("INSERT INTO threads_containers(job,container) VALUES(?,'')",(job['id'],))
        data=self.call('POST','me/threads',{'media_type':'TEXT','text':payload['caption'],'reply_to_id':parent})
        container=str(data.get('id',''))
        if not container.isdecimal():raise PublishError('uncertain')
        with self.ledger.db:
            self.ledger.db.execute('UPDATE threads_containers SET container=? WHERE job=?',(container,job['id']))
        return {'remoteId':'container:'+container}

    def reconcile(self,job,payload):
        self.identity(job)
        container=self.ledger.db.execute('SELECT * FROM threads_containers WHERE job=?',(job.get('id',''),)).fetchone()
        parent=str((payload.get('parent') or {}).get('remoteId') or '') if payload.get('companion') else None
        fields='id,text,permalink,timestamp,username,topic_tag'+(',replied_to' if parent else '')
        if container and not container['container']:
            # Ambiguous container create: never sent again.
            return {'status':'uncertain'}
        if container:
            if container['post']:
                job={**job,'remote_id':container['post']}
            elif container['attempted']:
                # Request may have succeeded before its response/checkpoint was lost.
                job={**job,'remote_id':None}
            else:
                status=self.call('GET',container['container'],{'fields':'id,status'})
                if status['status'] in ('ERROR','EXPIRED'):return {'status':'failed'}
                if status['status']=='PUBLISHED':
                    # Never republish; recover the exact caption from the account feed.
                    with self.ledger.db:self.ledger.db.execute('UPDATE threads_containers SET attempted=1 WHERE job=?',(job['id'],))
                    job={**job,'remote_id':None}
                elif status['status']=='FINISHED':
                    self.quota()
                    if self.pause_check():return {'status':'uncertain'}
                    with self.ledger.db:
                        self.ledger.db.execute('UPDATE threads_containers SET attempted=1 WHERE job=?',(job['id'],))
                    data=self.call('POST','me/threads_publish',{'creation_id':container['container']})
                    post=str(data['id'])
                    if not post.isdecimal():raise PublishError('uncertain')
                    with self.ledger.db:
                        self.ledger.db.execute('UPDATE threads_containers SET post=? WHERE job=?',(post,job['id']))
                    job={**job,'remote_id':post}
                else:return {'status':'uncertain'}
        elif (job.get('remote_id') or '').startswith('container:'):
            return {'status':'uncertain'}
        if job.get('remote_id'):
            post=self.call('GET',job['remote_id'],{'fields':fields})
        else:
            # An uncertain publish must be searched, never automatically recreated.
            data=self.call('GET','me/replies' if parent else 'me/threads',{'fields':fields,'limit':100})
            dispatch=dt.datetime.fromisoformat(job['dispatched_at']) if job.get('dispatched_at') else None
            matches=[]
            for item in data.get('data',[]):
                timestamp=dt.datetime.fromisoformat(item['timestamp'])
                if (caption_matches(item,payload['caption']) and dispatch and timestamp>=dispatch-dt.timedelta(minutes=2)
                        and (parent is None or str((item.get('replied_to') or {}).get('id',''))==parent)):matches.append(item)
            if len(matches)!=1:return {'status':'uncertain'}
            post=matches[0]
        url=urllib.parse.urlsplit(post.get('permalink') or '')
        if (not caption_matches(post,payload['caption']) or parent is not None and str((post.get('replied_to') or {}).get('id',''))!=parent
                or post.get('username','').lower()!=self.config['channels']['threads']['profileUrl'].split('@')[-1].rstrip('/').lower()
                or url.scheme!='https' or url.hostname not in ('threads.net','www.threads.net','threads.com','www.threads.com') or not post.get('timestamp')):
            return {'status':'uncertain'}
        return {'status':'confirmed','remoteId':str(post['id']),'permalink':post['permalink'],'publishedAt':post['timestamp']}


class Router:
    def __init__(self,buffer,threads,bluesky=None,facebook=None,instagram=None):self.buffer,self.threads,self.bluesky,self.facebook,self.instagram=buffer,threads,bluesky,facebook,instagram
    def route(self,job):
        if job['platform']=='instagram' and self.configured_route(job)=='instagram':
            if self.instagram is None:raise PublishError('rejected')
            return self.instagram
        if job['platform']=='facebook':
            if self.facebook is None:raise PublishError('rejected')
            return self.facebook
        if job['platform']=='bluesky':
            if self.bluesky is None:raise PublishError('rejected')
            return self.bluesky
        return self.threads if job['platform']=='threads' else self.buffer
    def configured_route(self,job):
        channel = self.buffer.config['channels'].get(job['platform'],{})
        # A direct Instagram identity must never fall through to Buffer on mismatch.
        if channel.get('route')=='instagram' and str(channel.get('accountId'))!=str(job.get('account')):
            raise PublishError('authorization')
        return channel.get('route')
    def publish(self,job,payload):return self.route(job).publish(job,payload)
    def reconcile(self,job,payload):return self.route(job).reconcile(job,payload)
