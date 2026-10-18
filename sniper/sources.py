"""Public game discovery/metrics, no credentialed access and no SteamDB scraping.
Sources may block GitHub runner IPs or change their schema: failures are reported, not treated as 0 players.
"""
import asyncio, random, re, uuid, json
from datetime import datetime, timezone
import httpx
from bs4 import BeautifulSoup
from .freshness import parse_date, recent

HEADERS={'User-Agent':'GameSniper/2.0 (open-source game statistics monitor)',
         'Accept':'application/json,text/html;q=0.9,*/*;q=0.8','Accept-Language':'en-US,en;q=0.9'}
TIMEOUT=httpx.Timeout(14,connect=6)
TERMS=['simulator','obby','survival','tycoon','horror','steal','tower','racing','escape','brainrot','clicker','fishing','rpg','pvp','anime','adventure','incremental','parkour','idle','minigame']

def discover_universes(obj):
    found={}
    def walk(node, depth=0):
        if depth>9:return
        if isinstance(node,list):
            for x in node[:400]:walk(x,depth+1)
        elif isinstance(node,dict):
            uid=node.get('universeId') or node.get('universeID') or node.get('universe_id')
            if not uid and node.get('rootPlaceId'):uid=node.get('id')
            if uid and str(uid).isdigit():
                found[str(uid)]={'gid':str(uid), 'platform':'roblox',
                                  'name':str(node.get('name') or node.get('displayName') or '')}
            for v in node.values():
                if isinstance(v,(dict,list)):walk(v,depth+1)
    walk(obj)
    return list(found.values())

async def roblox_discovery(client, limit=220):
    """Broader early-candidate search; no top-playing/top-grossing charts.

    Roblox discovery APIs are relevance-based, not a complete chronological index.
    We validate each returned universe's real creation date in the engine.
    """
    errors=[];games={};session=str(uuid.uuid4())
    try:
        r=await client.get('https://apis.roblox.com/explore-api/v1/get-sorts',
                           params={'sessionId':session,'device':'computer','country':'all'})
        r.raise_for_status();sorts=[]
        def find_sorts(value,depth=0):
            if depth>8:return
            if isinstance(value,dict):
                sid=value.get('sortId')
                if sid:
                    label=' '.join(str(value.get(x) or '') for x in ('name','title','displayName','sortName','description','slug','sortId')).lower()
                    # Explicitly avoid large-chart feeds. They select established hits.
                    if any(word in label for word in ('up-and-coming','up and coming','hidden gem','new experience','new &','rising','fresh')):
                        sorts.append(str(sid))
                for v in value.values():
                    if isinstance(v,(list,dict)):find_sorts(v,depth+1)
            elif isinstance(value,list):
                for v in value[:100]:find_sorts(v,depth+1)
        find_sorts(r.json())
        for sort in list(dict.fromkeys(sorts))[:5]:
            try:
                r=await client.get('https://apis.roblox.com/explore-api/v1/get-sort-content',
                                   params={'sessionId':session,'sortId':sort})
                r.raise_for_status()
                for item in discover_universes(r.json()):games[item['gid']]=item
            except (httpx.HTTPError,ValueError) as exc:errors.append('Roblox emerging sort '+sort+': '+str(exc)[:95])
    except (httpx.HTTPError,ValueError) as exc:errors.append('Roblox discovery: '+str(exc)[:95])
    # Rotate searches to surface games outside established discover charts.
    # Date filtering happens only against real Roblox created timestamps downstream.
    terms=random.sample(TERMS, min(len(TERMS),6))
    for term in [f'new {t}' for t in terms[:4]]+terms[4:]:
        try:
            r=await client.get('https://apis.roblox.com/search-api/omni-search',
                               params={'SearchQuery':term,'SessionId':session})
            r.raise_for_status()
            for item in discover_universes(r.json()):games[item['gid']]=item
        except (httpx.HTTPError,ValueError) as exc:errors.append('Roblox search: '+str(exc)[:95])
    return list(games.values())[:limit],errors

async def roblox_place_to_universe(client,place_id):
    r=await client.get(f'https://apis.roblox.com/universes/v1/places/{int(place_id)}/universe')
    r.raise_for_status();return str(r.json()['universeId'])

async def roblox_metrics(client, ids):
    found=[];errors=[]
    for i in range(0,len(ids),40):
        group=ids[i:i+40]
        try:
            r=await client.get('https://games.roblox.com/v1/games',params={'universeIds':','.join(group)})
            r.raise_for_status()
            for item in r.json().get('data',[]):
                uid=str(item['id']);place=item.get('rootPlaceId') or uid
                found.append({'platform':'roblox','gid':uid,'name':item.get('name') or f'Roblox {uid}',
                    'url':f'https://www.roblox.com/games/{place}',
                    'image':f'https://www.roblox.com/asset-thumbnail/image?assetId={place}&width=420&height=420&format=png',
                    'players':int(item.get('playing') or 0),'visits':item.get('visits'),
                    'created_at':item.get('created') or '', 'favorites':item.get('favoritedCount')})
        except (httpx.HTTPError,ValueError,KeyError) as exc:errors.append('Roblox metrics: '+str(exc)[:95])
    # Votes are public but may be rate-limited; absence is unknown, not zero.
    for i in range(0,len(found),40):
        group=found[i:i+40]
        try:
            r=await client.get('https://games.roblox.com/v1/games/votes',params={'universeIds':','.join(g['gid'] for g in group)})
            r.raise_for_status()
            votes={str(x['id']):x for x in r.json().get('data',[]) if x.get('id')}
            for item in group:
                v=votes.get(item['gid'])
                if v:item['up_votes']=v.get('upVotes');item['down_votes']=v.get('downVotes')
        except (httpx.HTTPError,ValueError,KeyError) as exc:errors.append('Roblox votes: '+str(exc)[:80])
    return found,errors

async def steam_discovery(client, limit=160, max_age_days=30, now=None):
    """Find genuine recent releases by release-date listing, NOT popularity charts.

    Steam's store rows supply dates, which we validate before saving candidates.
    Metadata is cross-checked through appdetails where available.
    """
    import time
    now=now or time.time();games={};errors=[]
    # Steam's own chronological store search; avoid Popular New Releases,
    # which mixes in long-running titles, bundles, and older top sellers.
    for start in (0,50,100):
        try:
            r=await client.get('https://store.steampowered.com/search/',
                 params={'sort_by':'Released_DESC','category1':'998','os':'win',
                         'ignore_preferences':'1','start':str(start),'count':'50'})
            r.raise_for_status();soup=BeautifulSoup(r.text,'html.parser')
            for a in soup.select('a.search_result_row')[:60]:
                gid=str(a.get('data-ds-appid') or '')
                if not gid.isdigit():continue
                title=a.select_one('.title');date=a.select_one('.search_released')
                if not title or not date:continue
                released=date.get_text(' ',strip=True)
                dateval=parse_date(released)
                if not dateval or not recent({'created_at':released}, now, max_age_days):continue
                image=a.select_one('img')
                games[gid]={'platform':'steam','gid':gid,'name':title.get_text(' ',strip=True),
                            'created_at':dateval.date().isoformat(),
                            'image':image.get('src','') if image else '',
                            'url':f'https://store.steampowered.com/app/{gid}/'}
        except (httpx.HTTPError,ValueError) as exc:
            errors.append('Steam recent releases: '+str(exc)[:95])
    return list(games.values())[:limit],errors

async def steam_player(client,game):
    gid=game['gid']
    try:
        r=await client.get('https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/',params={'appid':gid})
        r.raise_for_status();body=r.json().get('response',{})
        if body.get('result')!=1 or 'player_count' not in body:return None,f'Steam {gid}: unavailable player count'
        return {'platform':'steam','gid':gid,'name':game.get('name') or f'Steam {gid}',
                'url':f'https://store.steampowered.com/app/{gid}/',
                'image':game.get('image') or f'https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{gid}/header.jpg',
                'players':int(body['player_count'])},None
    except (httpx.HTTPError,ValueError) as exc:return None,f'Steam {gid}: '+str(exc)[:85]

async def steam_metrics(client,games):
    semaphore=asyncio.Semaphore(5)
    async def one(game):
        async with semaphore:return await steam_player(client,game)
    results=await asyncio.gather(*(one(g) for g in games))
    return [v for v,e in results if v],[e for v,e in results if e][:25]

async def steam_metadata(client,gid):
    """Release date & review totals. Steam public review API switched in Oct 2026."""
    output={};errors=[]
    try:
        r=await client.get('https://store.steampowered.com/api/appdetails',params={'appids':gid,'cc':'us','l':'en'},
                           headers={'Cookie':'birthtime=568022401;wants_mature_content=1'})
        r.raise_for_status()
        item=r.json().get(gid,{})
        if item.get('success'):
            data=item.get('data') or {}
            if data.get('type') and data.get('type')!='game':output['non_game']=True
            output['name']=data.get('name') or None
            output['created_at']=(data.get('release_date') or {}).get('date') or ''
            output['image']=data.get('header_image') or ''
    except (httpx.HTTPError,ValueError) as exc:errors.append('Steam details '+gid+': '+str(exc)[:90])
    try:
        # Current Steamworks IUserReviewsService; note input_json, NOT deprecated /appreviews.
        r=await client.get('https://api.steampowered.com/IUserReviewsService/GetAppReviews/v1/',
             params={'input_json':json.dumps({'appid':int(gid),'num_per_page':1,'languages':['all'],'review_type':0})})
        r.raise_for_status()
        data=r.json();body=data.get('response') or data
        summary=body.get('query_summary') or {}
        if 'total_positive' in summary and 'total_negative' in summary:
            output['positive_reviews']=int(summary['total_positive']);output['negative_reviews']=int(summary['total_negative'])
            output['rating_label']=summary.get('review_score_desc') or ''
    except (httpx.HTTPError,ValueError) as exc:errors.append('Steam reviews '+gid+': '+str(exc)[:90])
    return output,errors
