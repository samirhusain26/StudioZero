"""Select reviewed batch content on Pi; assemble exact confirmed predecessor clips.

FFmpeg stream copying is lightweight. Remotion rendering stays on the Mac.
Cloudflare Pages deployment requires approved access; no paid products are used.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from buffer_adapter import PublishError
from runner import slots


def eligible(ep, now):
    v=ep.get('verification') or {}
    if v.get('status')!='verified' or not v.get('sourceHash') or not ep.get('answer') or not ep.get('provenance',{}).get('ids'):
        return False
    date=ep['provenance'].get('playDate')
    if not date:
        return not ep.get('event')
    try:
        parsed=dt.date.fromisoformat(date)
        if parsed.isoformat()!=date: return False
        cutoff=(now-dt.timedelta(hours=12)).date()-dt.timedelta(days=4)
        return parsed<=cutoff and (not ep.get('event') or ep['event'].get('playDate')==date)
    except ValueError:
        return False


def caption(ep, platform, format, previous=None):
    query=urllib.parse.urlencode({'utm_source':platform,'utm_medium':'organic_social','utm_campaign':'social_puzzles_v1','utm_content':ep['id']+'_'+format})
    url='https://www.scalargame.com'+ep['deepLink']+'?'+query
    hook=' '.join(ep['question'])
    reminder=(f"Previous episode: {' '.join(previous['episode']['question'])} Answer: {previous['episode']['answer']}. {previous['permalink']}" if previous else '')
    if platform=='x':
        # Caption including URL stays within standard X length; URL counts as 23 chars.
        body=hook[:130]+'\nGuess along. '+('Reveal in the video.' if format=='self-contained' else 'Look for the next published episode.')+'\n'+url
    else:
        invite=('Play four free daily puzzles at scalargame.com.' if platform in ('instagram','youtube','tiktok') else 'Play four free daily puzzles: '+url)
        body='\n\n'.join(x for x in [hook+' Guess along.', 'Archive challenge. '+('Reveal in this video.' if format=='self-contained' else 'Look for the next published episode.'),reminder,invite,'#geography #puzzles #scalargame'] if x)
    return body,url


class BatchPreparer:
    def __init__(self, ledger, config, state, catalog_path, assembler=None, clock=None):
        self.ledger,self.config,self.state=ledger,config,Path(state)
        raw=catalog_path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=(config.get('approval') or {}).get('catalogSha256'):
            raise ValueError('Batch catalogue not approved')
        self.catalog_raw=raw
        self.catalog=json.loads(raw)
        if not self.catalog.get('rightsReviewed'):
            raise ValueError('Batch rights not reviewed')
        if len({e['id'] for e in self.catalog['episodes']})!=len(self.catalog['episodes']):
            raise ValueError('Duplicate batch episode')
        self.assembler=assembler or self.assemble
        self.clock=clock or (lambda:dt.datetime.now(dt.timezone.utc))

    def fill(self, now):
        self.exhausted=[]
        order=['scalar','continuum','whenabouts','tectonic']
        for platform,c in self.config['channels'].items():
            if not c['enabled']: continue
            # Route migrations may change the provider's account identifier.
            # Keep former IDs only for duplicate prevention, never reconciliation
            # or selecting a chain predecessor from another account.
            accounts = [c['accountId'], *c.get('previousAccountIds', [])]
            placeholders = ','.join('?' for _ in accounts)
            used=[r[0] for r in self.ledger.db.execute(
                'SELECT episode FROM jobs WHERE platform=? AND account IN ('+placeholders+') ORDER BY slot',
                (platform, *accounts))]
            for slot in slots(self.config,now):
                if self.ledger.db.execute('SELECT 1 FROM jobs WHERE platform=? AND account=? AND slot=?',(platform,c['accountId'],slot)).fetchone():continue
                pool=[e for e in self.catalog['episodes'] if e['id'] not in used and eligible(e,now)]
                if not pool:
                    self.exhausted.append(platform)
                    with self.ledger.db:self.ledger.event(None,'content_exhausted',platform)
                    break
                last=next((e for e in self.catalog['episodes'] if used and e['id']==used[-1]),None)
                start=(order.index(last['game'])+1)%4 if last else 0
                episode=next((e for i in range(4) for e in pool if e['game']==order[(start+i)%4]),None)
                mode=self.config['format']
                if mode=='comparison': mode='self-contained' if len(used)%2==0 else 'chained'
                # Final batch item reveals itself rather than leaving an unanswered chain.
                if len(pool)==1: mode='self-contained'
                payload={'episode':episode,'format':mode,'catalogSha256':self.config['approval']['catalogSha256']}
                self.ledger.enqueue(platform,c['accountId'],slot,payload)
                used.append(episode['id'])

    def prepare(self, job, payload):
        ep=payload['episode']
        now=self.clock()
        if not eligible(ep,now): raise PublishError('rejected')
        if payload['catalogSha256']!=self.config['approval']['catalogSha256']: raise PublishError('rejected')
        rows=self.ledger.db.execute("SELECT * FROM jobs WHERE platform=? AND account=? AND status='confirmed' AND slot<? AND published_at<? ORDER BY published_at DESC LIMIT 1",(job['platform'],job['account'],job['slot'],now.isoformat())).fetchall()
        previous=None
        if payload['format']=='chained' and rows:
            row=rows[0]
            if row['remote_id'] and row['permalink']:
                previous={'episode':json.loads(row['payload'])['episode'],'remoteId':row['remote_id'],'permalink':row['permalink'],'publishedAt':row['published_at']}
        parts=([ep['id']+':self'] if payload['format']=='self-contained' else [ep['id']+':hook', previous['episode']['id']+':reminder' if previous else 'intro',ep['id']+':challenge'])
        if any(p not in self.catalog['clips'] for p in parts):
            # Cross-batch predecessor not rendered: safe self-contained fallback, explicit in ledger.
            payload['format']='self-contained';previous=None;parts=[ep['id']+':self']
        text,url=caption(ep,job['platform'],payload['format'],previous)
        if job['platform']=='threads' and self.config['channels']['threads'].get('threadsFormat')=='native_poll':
            # Polls are text-only and cannot carry the motion video. Explicit edition.
            options=ep.get('choices') or [o['name'] for o in ep.get('options',[])]
            if any(len(v.encode())>25 for v in options) or not 2<=len(options)<=4:raise PublishError('rejected')
            question=' '.join(ep['question'])
            if len(ep.get('options',[]))==3:question+=' Which country comes first?'
            reminder=(f"Previously: {' '.join(previous['episode']['question'])} Answer: {previous['episode']['answer']}.\n{previous['permalink']}\n" if previous else 'A new Scalar archive & reference challenge.\n')
            # A poll never reveals its own correct option in the caption.
            text=f'{question}\n\n{reminder}\nGuess in the poll. Play the daily games at scalargame.com.'
            if payload['format']=='self-contained':text+='\n\nAnswer: '+ep['answer']
            if len(text)>500:raise PublishError('rejected')
            return {**payload,'caption':text,'link':url,'previous':previous,'nativePoll':options,'media':None,'metadata':{}}
        media=self.assembler(parts)
        metadata={}
        if job['platform']=='instagram':metadata={'instagram':{'type':'reel','shouldShareToFeed':True}}
        if job['platform']=='youtube':metadata={'youtube':{'title':' '.join(ep['question'])[:95],'categoryId':'27','privacy':'public','madeForKids':False,'license':'youtube','notifySubscribers':True,'embeddable':True,'isAiGenerated':False}}
        if job['platform']=='bluesky':
            text='\n'.join([' '.join(ep['question']), 'Archive challenge. Guess along; reveal in this video.' if payload['format']=='self-contained' else 'Archive challenge. Guess along.', url])
            if len(text)>300:raise PublishError('rejected')
        return {**payload,'caption':text,'link':url,'previous':previous,'media':media,'metadata':metadata}

    def download(self, clip):
        path=clip['path']
        if not re.fullmatch(r'clips/[a-zA-Z0-9-]+\.mp4',path) or not clip.get('sha256'):
            raise PublishError('media')
        target=self.state/'site'/path
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==clip['sha256']:return target
        base=self.config['media']['baseUrl']
        if not base or urllib.parse.urlsplit(base).scheme!='https':raise PublishError('media')
        temp=target.with_suffix('.tmp')
        total=0;digest=hashlib.sha256()
        try:
            with urllib.request.urlopen(base.rstrip('/')+'/'+path,timeout=30) as response,temp.open('wb') as output:
                if urllib.parse.urlsplit(response.url).hostname!=urllib.parse.urlsplit(base).hostname:raise PublishError('media')
                while chunk:=response.read(65536):
                    total+=len(chunk)
                    if total>24_000_000:raise PublishError('media')
                    digest.update(chunk);output.write(chunk)
            if digest.hexdigest()!=clip['sha256']:raise PublishError('media')
            temp.replace(target)
            return target
        except OSError: raise PublishError('media') from None

    def assemble(self, parts):
        # Pages deployments replace the site's file manifest. Preserve the complete
        # approved input catalogue before deploying assembled output.
        for clip in self.catalog['clips'].values():self.download(clip)
        clips=[self.catalog['clips'][p] for p in parts]
        sources=[self.download(c) for c in clips]
        key=hashlib.sha256('|'.join(c['sha256'] for c in clips).encode()).hexdigest()
        site=self.state/'site';out=site/'published'/f'{key}.mp4';out.parent.mkdir(parents=True,exist_ok=True)
        (site/'catalog.json').write_bytes(self.catalog_raw)
        (site/'index.html').write_text('<!doctype html><html lang="en"><meta name="robots" content="noindex"><title>Scalar puzzle media</title><h1>Scalar puzzle media</h1><a href="https://www.scalargame.com">Play the daily set</a></html>')
        if not out.exists():
            concat=self.state/'concat.txt'
            concat.write_text(''.join("file '"+str(p)+"'\n" for p in sources))
            result=subprocess.run(['/usr/bin/ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy',*(['-an'] if len(parts)>1 else []),'-movflags','+faststart',str(out)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=90)
            if result.returncode or not out.exists() or out.stat().st_size>24_000_000:
                raise PublishError('media')
        probe=subprocess.run(['/usr/bin/ffprobe','-v','error','-show_streams','-show_format','-of','json',str(out)],capture_output=True,text=True,timeout=30)
        try:
            from check_media import validate
            data=json.loads(probe.stdout)
            validate(out,data)
            if probe.returncode or abs(float(data['format']['duration'])-30)>0.1:raise ValueError('Incomplete output')
        except (ValueError,KeyError):
            out.unlink(missing_ok=True)
            raise PublishError('media')
        digest=hashlib.sha256(out.read_bytes()).hexdigest()
        self.deploy(site)
        url=self.config['media']['baseUrl'].rstrip('/')+'/published/'+out.name
        from verify_delivery import verify
        verify(url,digest)
        return {'url':url,'sha256':digest,'rightsReviewed':True}

    def deploy(self, site):
        return deploy_site(self.ledger, self.config, site)


STAGE_FILES=6  # new files per wrangler run: wrangler holds a whole upload batch in memory and the Pi has ~400 MB


def deploy_site(ledger, config, site, served=None):
    # Retain existing files on every deployment. Never delete files behind uncertain requests.
    files=sorted(p for p in site.rglob('*') if p.is_file())
    if len(files)>19000 or any(p.stat().st_size>24_000_000 for p in files):raise PublishError('media')
    project=config['media']['pagesProject']
    if not re.fullmatch('[a-z0-9-]{1,50}',project):raise PublishError('media')
    # Pages skips files it already holds, so deploying a few new files at a time keeps each upload small: every
    # stage is the files already served plus the next few new ones, and the last stage is the whole site.
    base=(config['media'].get('baseUrl') or '').rstrip('/')
    served=served or publicly_served
    new=[p for p in files if not (base and served(base+'/'+p.relative_to(site).as_posix(),p.stat().st_size))]
    stages=[new[i:i+STAGE_FILES] for i in range(0,len(new),STAGE_FILES)] or [[]]
    stage_dir=site.parent/'site-stage'
    try:
        for n in range(len(stages)):
            later={p for stage in stages[n+1:] for p in stage}
            if not later:
                _deploy(ledger,config,site,project)
                break
            shutil.rmtree(stage_dir,ignore_errors=True)
            for p in files:
                if p not in later:
                    target=stage_dir/p.relative_to(site)
                    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                    try:os.link(p,target)
                    except OSError:shutil.copyfile(p,target)
            print(json.dumps({'staticDeploymentStage':n+1,'of':len(stages),'newFiles':len(stages[n])}))
            _deploy(ledger,config,stage_dir,project)
    finally:
        shutil.rmtree(stage_dir,ignore_errors=True)


def publicly_served(url, size):
    """True when the public URL already returns this file (Pages answers unknown paths with an HTML page)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url,method='HEAD',headers={'User-Agent':'ScalarMediaVerifier/1.0'}),timeout=15) as r:
            # Pages sends no Content-Length on HEAD; when it does, it must match.
            length=r.headers.get('Content-Length')
            return r.headers.get_content_type()!='text/html' and length in (None,str(size))
    except OSError:
        return False


def _deploy(ledger, config, site, project):
    with ledger.db:
        ledger.db.execute('CREATE TABLE IF NOT EXISTS deployments(at REAL)')
        count=ledger.db.execute('SELECT count(*) FROM deployments WHERE at>?',(__import__('time').time()-31*86400,)).fetchone()[0]
        if count>=120:raise PublishError('budget')
        # Count attempts conservatively, including uncertain deployment outcomes.
        ledger.db.execute('INSERT INTO deployments VALUES(?)',(__import__('time').time(),))
    credentials=Path(os.environ.get('CREDENTIALS_DIRECTORY','/nonexistent'))
    env={**os.environ,'CLOUDFLARE_API_TOKEN':(credentials/'CLOUDFLARE_API_TOKEN').read_text().strip(),
         'CLOUDFLARE_ACCOUNT_ID':config['media']['cloudflareAccountId'],'WRANGLER_SEND_METRICS':'false'}
    result=subprocess.run(['/opt/scalar-social/node_modules/.bin/wrangler','pages','deploy',str(site),'--project-name',project,'--branch','main','--commit-dirty=true'],cwd=site.parent,env=env,capture_output=True,text=True,timeout=120)
    if result.returncode:
        # Never log vendor output: it may contain credentials or response bodies.
        codes=re.findall(r'\[code:\s*(\d+)\]',result.stdout+result.stderr)
        print(json.dumps({'staticDeploymentFailed':True,'exitCode':result.returncode,'apiErrorCodes':codes}))
        raise PublishError('media')
    # Exit 0 is not enough: wrangler exits 0 when the kernel kills its upload process for memory, deploying nothing.
    url=re.search(r'https://[0-9a-f]{8}\.'+re.escape(project)+r'\.pages\.dev',result.stdout+result.stderr)
    if not url:
        print(json.dumps({'staticDeploymentUnconfirmed':True,'tail':deploy_tail(result.stdout+result.stderr,env['CLOUDFLARE_API_TOKEN'])}))
        raise PublishError('media')
    print(json.dumps({'staticDeployment':url.group(0)}))


def deploy_tail(output, token, lines=6):
    """The last lines of wrangler output with the token and any long credential-like run removed."""
    text=output.replace(token,'[token]') if token else output
    text=re.sub(r'[A-Za-z0-9_\-]{32,}','[redacted]',text)
    return [line.strip()[:200] for line in text.splitlines() if line.strip()][-lines:]
