"""Idempotent cloud scan; persists across ephemeral GitHub runners in tracked JSON."""
import argparse, asyncio, copy, json, os, time
from datetime import datetime, timezone
from pathlib import Path
import httpx
from . import sources
from .discord import build_embed
from .scoring import evaluate

ROOT=Path(__file__).resolve().parent.parent
from .privacy import read_bundle, write_bundle, get_key
STATE=ROOT/'docs/secure.enc.json'
CONFIG=ROOT/'config.json'

def load_config():
    raw=json.loads(CONFIG.read_text(encoding='utf-8'))
    raw.setdefault('scan',{});raw.setdefault('alerts',{});raw.setdefault('watchlist',{})
    private_watchlist = os.environ.get('GAMESNIPER_PRIVATE_WATCHLIST_JSON', '').strip()
    if private_watchlist:
        data = json.loads(private_watchlist)
        if not isinstance(data, dict): raise ValueError('Private watchlist must be a JSON object')
        raw['watchlist'] = data
    return raw

def new_state(): return {'version':2,'games':{},'alerts':[],'meta':{'last_scan':None,'errors':[],'successful_games':0}}

def load_state():
    if not STATE.exists():return new_state()
    obj=read_bundle(STATE,get_key())['state']
    if obj.get('version') != 2:raise ValueError('Unexpected state schema; refuse to overwrite previous history')
    return obj

def save_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    temp.replace(path)

def priority_select(games, pinned_ids, limit, new_per_cycle, now):
    """Prioritize pinned, new, high-momentum and round-robin older titles."""
    games=list(games)
    pinned=[g for g in games if g['gid'] in pinned_ids]
    remaining=[g for g in games if g['gid'] not in pinned_ids]
    selected=pinned[:limit]
    room=max(0,limit-len(selected))
    incoming=sorted([g for g in remaining if not g.get('last_polled')],key=lambda g:g.get('discovered',now),reverse=True)
    newest=incoming[:min(room,new_per_cycle)]
    selected+=newest;room=max(0,limit-len(selected))
    excluded=set(g['gid'] for g in selected)
    remaining=[g for g in remaining if g['gid'] not in excluded]
    # Reserve some capacity for early breakouts then use oldest-poll-first to avoid starvation.
    elite=sorted(remaining,key=lambda g:(g.get('signal',{}).get('score',0),g.get('players') or 0),reverse=True)[:min(room//3,20)]
    selected+=elite;room=max(0,limit-len(selected));excluded.update(g['gid'] for g in elite)
    remaining=[g for g in remaining if g['gid'] not in excluded]
    selected+=sorted(remaining,key=lambda g:g.get('last_polled') or 0)[:room]
    return selected

def safe_pinned(config):
    w=config.get('watchlist',{})
    return {'roblox':{str(int(x)) for x in w.get('roblox_universe_ids',[]) if str(x).isdigit()},
            'steam':{str(int(x)) for x in w.get('steam_app_ids',[]) if str(x).isdigit()}}

def merge_candidates(state, found, now, capacity=450):
    for game in found:
        platform=game.get('platform');gid=str(game.get('gid',''))
        if platform not in ('roblox','steam') or not gid.isdigit():continue
        key=platform+':'+gid
        entry=state['games'].setdefault(key,{'platform':platform,'gid':gid,'discovered':now,'history':[]})
        if game.get('name'):entry['name']=game['name']
        if game.get('image'):entry['image']=game['image']
        if game.get('url'):entry['url']=game['url']
    # Discard unmonitored candidates first, but retain existing history if possible.
    if len(state['games'])>capacity:
        ordered=sorted(state['games'],key=lambda k:(bool(state['games'][k].get('history')),
            state['games'][k].get('signal',{}).get('score',0),state['games'][k].get('discovered',0)),reverse=True)
        state['games']={key:state['games'][key] for key in ordered[:capacity]}

def apply_metric(state,metric,now):
    key=metric['platform']+':'+str(metric['gid'])
    record=state['games'].get(key)
    if record is None:
        merge_candidates(state,[metric],now,100000);record=state['games'][key]
    for k,v in metric.items():
        if k in ('players','visits','favorites','created_at','up_votes','down_votes','url','name','image') and v is not None:
            record[k]=v
    record['players']=int(metric['players'])
    record['last_polled']=now
    history=record.setdefault('history',[])
    if not history or history[-1][0] < now-60:
        history.append([now,record['players']])
    else:history[-1]=[now,record['players']]
    # Keep a little over a day; the farthest window needs a sample from >=24h ago.
    history[:]=[p for p in history if p[0]>=now-28*3600]
    record['signal']=evaluate(history,now)
    return record

def qualify(record, config):
    signal=record.get('signal') or {}; tier=signal.get('tier','monitoring')
    if tier not in ('scout','breakout','viral'):return False
    settings=config['alerts']
    if tier=='scout' and not settings.get('include_scout',True):return False
    g=signal.get('windows',{}).get('15m') or signal.get('windows',{}).get('1h')
    return bool(g and g['delta']>=int(settings.get('minimum_player_gain',35))
        and g['percent']>=float(settings.get('minimum_growth_percent',60)))

def pending_alerts(state,config,now):
    rank={'scout':1,'breakout':2,'viral':3}
    result=[];cooldown=int(config['alerts'].get('cooldown_minutes',120))*60
    for key,game in state['games'].items():
        if not game.get('last_polled') or now-game['last_polled']>600 or not qualify(game,config):continue
        tier=game['signal']['tier'];previous=game.get('last_alert') or {}
        if previous and now-previous.get('time',0)<cooldown and rank.get(tier,0)<=rank.get(previous.get('tier'),0):continue
        result.append((key,game))
    return result

async def publish_alert(client,url,game,config,now):
    payload=build_embed(game,game['signal'],config['alerts'].get('primary_window','1h'),now)
    r=await client.post(url,json=payload,timeout=12)
    r.raise_for_status()
    return payload

def to_public(state,now):
    games=[]
    for game in state['games'].values():
        if not game.get('last_polled'):continue
        clean={key:game.get(key) for key in ('platform','gid','name','url','image','players','visits','favorites',
            'created_at','up_votes','down_votes','positive_reviews','negative_reviews','rating_label','discovered','last_polled')}
        clean['signal']=game.get('signal') or evaluate(game.get('history',[]),now)
        clean['history']=game.get('history',[])
        games.append(clean)
    games.sort(key=lambda g:(g.get('signal',{}).get('score',0),g.get('players') or 0),reverse=True)
    return {'version':2,'generated_at':now,'mode':'live','games':games[:450],
            'alerts':state.get('alerts',[])[-80:][::-1],
            'status':{'tracked':len(games),'last_scan':state['meta'].get('last_scan'),
                      'successful_games':state['meta'].get('successful_games',0),
                      'webhook_configured':state['meta'].get('webhook_configured',False),
                      'source_errors':state['meta'].get('errors',[])[:12]}}

async def run_once(config=None, state=None, client=None, now=None, discover=None):
    config=config or load_config();state=state or load_state();now=int(now or time.time())
    own_client=client is None
    client=client or httpx.AsyncClient(headers=sources.HEADERS, timeout=sources.TIMEOUT,
                                      follow_redirects=True,limits=httpx.Limits(max_connections=12))
    errors=[];successful=0
    try:
        pinned=safe_pinned(config)
        # Discovery every 15 minutes, on first run, or when only a few candidates remain.
        scan_count=int(state['meta'].get('scan_count',0))
        discover = (scan_count % 3==0) if discover is None else discover
        found=[]
        if discover:
            for coro in (sources.roblox_discovery(client),sources.steam_discovery(client)):
                try:
                    games,issues=await coro;found+=games;errors+=issues
                except Exception as exc:errors.append(f'Discovery unavailable: {type(exc).__name__}: {str(exc)[:90]}')
        for gid in pinned['roblox']:
            found.append({'platform':'roblox','gid':gid})
        for gid in pinned['steam']:
            found.append({'platform':'steam','gid':gid})
        for placeid in config.get('watchlist',{}).get('roblox_place_ids',[]):
            try:
                uid=await sources.roblox_place_to_universe(client,placeid)
                pinned['roblox'].add(uid);found.append({'platform':'roblox','gid':uid})
            except Exception as exc:errors.append(f'Roblox place {placeid}: {type(exc).__name__}')
        merge_candidates(state,found,now,int(config['scan'].get('candidate_limit',450)))
        selected={}
        for platform,limit_key,limit_default in [('roblox','roblox_limit',110),('steam','steam_limit',35)]:
            pool=[g for g in state['games'].values() if g['platform']==platform]
            selected[platform]=priority_select(pool,pinned[platform],int(config['scan'].get(limit_key,limit_default)),
                            int(config['scan'].get('new_per_cycle',40)),now)
        try:
            metrics,issues=await sources.roblox_metrics(client,[g['gid'] for g in selected['roblox']]);errors+=issues
            for item in metrics:apply_metric(state,item,now);successful+=1
        except Exception as exc:errors.append('Roblox scan failed: '+str(exc)[:100])
        try:
            metrics,issues=await sources.steam_metrics(client,selected['steam']);errors+=issues
            for item in metrics:apply_metric(state,item,now);successful+=1
        except Exception as exc:errors.append('Steam scan failed: '+str(exc)[:100])
        # Enrich only a handful of Steam games per run (rate limits), even if metadata missing.
        eligible=[g for g in selected['steam'] if state['games'].get('steam:'+g['gid'],{}).get('last_polled') and
                  now-state['games']['steam:'+g['gid']].get('last_details',0)>12*3600]
        eligible.sort(key=lambda g:state['games']['steam:'+g['gid']].get('last_details',0))
        for game in eligible[:int(config['scan'].get('steam_details_per_cycle',7))]:
            try:
                details,issues=await sources.steam_metadata(client,game['gid']);errors+=issues
                saved=state['games']['steam:'+game['gid']]
                for k,v in details.items():
                    if v is not None and k!='non_game':saved[k]=v
                saved['last_details']=now
            except Exception as exc:errors.append('Steam details failed: '+str(exc)[:80])
        webhook=(os.getenv('DISCORD_WEBHOOK_URL') or '').strip()
        for key,game in pending_alerts(state,config,now):
            if not webhook:continue
            try:
                await publish_alert(client,webhook,game,config,now)
                game['last_alert']={'time':now,'tier':game['signal']['tier']}
                state['alerts'].append({'ts':now,'key':key,'name':game.get('name'),'platform':game['platform'],
                                        'tier':game['signal']['tier'],'players':game['players'],'url':game.get('url')})
            except (httpx.HTTPError,ValueError) as exc:
                errors.append(f'Discord send failed: {type(exc).__name__} (webhook URL redacted)')
        state['alerts']=state['alerts'][-120:]
        state['meta']={'last_scan':now,'successful_games':successful,'errors':errors[:16],
                       'webhook_configured':bool(webhook), 'scan_count':scan_count+1}
        return state,to_public(state,now)
    finally:
        if own_client:await client.aclose()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dry-run',action='store_true',help='Scan but do not write or send Discord')
    args=parser.parse_args()
    if args.dry_run:os.environ.pop('DISCORD_WEBHOOK_URL',None)
    # Fail closed before discovery, network calls, or Discord delivery.
    key=get_key() if not args.dry_run else None
    state,public=asyncio.run(run_once())
    print(f'Observed {public["status"]["successful_games"]} games; currently tracking {public["status"]["tracked"]}')
    for e in public['status']['source_errors']:print('WARN:',e)
    if not args.dry_run:
        write_bundle(STATE, {'state':state,'dashboard':public}, key)

if __name__=='__main__':main()
