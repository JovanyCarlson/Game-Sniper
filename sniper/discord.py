"""Discord webhook formatter. Webhook secret never goes into static output."""
import html
from datetime import datetime,timezone

COLORS={'scout':0xE6AA50,'breakout':0x42CBA1,'viral':0xA970FF}
LABELS={'15m':'15 MIN','1h':'1 HOUR','6h':'6 HOURS','24h':'24 HOURS'}

def comma(value):
    return f'{int(value):,}' if value is not None else 'Not available'

def build_embed(game, signal, primary='1h', generated=None):
    platform=game['platform'].upper();tier=signal['tier']
    title=str(game.get('name') or f'{platform} game {game["gid"]}')[:250]
    # User-controlled game titles must not mention Discord roles.
    title=title.replace('@','＠')
    meta=game.get('created_at') or ''
    date_label='Created' if platform=='ROBLOX' else 'Released'
    fields=[{'name':'👥 Active players now','value':comma(game.get('players')),'inline':True},
            {'name':f'📅 {date_label}','value':meta[:60] or 'Not available','inline':True},
            {'name':'👁️ Total visits' if platform=='ROBLOX' else '👁️ Total visits',
             'value':comma(game.get('visits')) if platform=='ROBLOX' else 'Not public on Steam','inline':True}]
    if platform=='ROBLOX':
        up,down=game.get('up_votes'),game.get('down_votes')
        rating=f'{round(100*up/(up+down),1)}% 👍 ({comma(up)} up / {comma(down)} down)' if isinstance(up,int) and isinstance(down,int) and up+down>0 else 'Not available'
    else:
        positive,negative=game.get('positive_reviews'),game.get('negative_reviews')
        rating=(f'{round(100*positive/(positive+negative),1)}% positive '
               f'({comma(positive+negative)} reviews)' if isinstance(positive,int) and isinstance(negative,int) and positive+negative>0 else 'Not available')
        if game.get('rating_label'):rating+=f' · {game["rating_label"]}'
    fields.append({'name':'👍 Like ratio' if platform=='ROBLOX' else '⭐ Steam reviews',
                   'value':rating[:1024],'inline':False})
    for w in ('15m','1h','6h','24h'):
        period=signal['windows'].get(w)
        name=('⭐ ' if w==primary else '📈 ')+'Last '+LABELS[w]
        value=(f'{period["delta"]:+,} players · {period["percent"]:+.1f}%'
               if period else 'Collecting history…')
        fields.append({'name':name,'value':value,'inline':True})
    image=game.get('image','')
    embed={'title':title,'url':game['url'],'description':f'**{platform} · {tier.upper()} SIGNAL**  |  Sniper score: **{signal["score"]}/100**',
           'color':COLORS.get(tier,0x89A0B6), 'fields':fields,
           'footer':{'text':'GameSniper • Player counts are sampled, not live-streamed • Open dashboard to switch timeframes'},
           'timestamp':datetime.fromtimestamp(generated or datetime.now(timezone.utc).timestamp(),timezone.utc).isoformat()}
    if isinstance(image,str) and image.startswith('https://'):embed['thumbnail']={'url':image}
    return {'username':'GameSniper','allowed_mentions':{'parse':[]},'embeds':[embed]}
