"""Pure momentum signals, with no fabricated timeframe comparisons."""
from datetime import datetime, timezone
import math

WINDOWS = {'15m': 900, '1h': 3600, '6h': 21600, '24h': 86400}

def window_growth(history, window, now=None):
    if not history or window not in WINDOWS: return None
    horizon = WINDOWS[window]
    latest = history[-1]
    now = now or latest[0]
    # Avoid treating a 15-minute gain as if we measured the entire past hour.
    if latest[0] < now - 300: return None
    candidates = [row for row in history[:-1] if now - horizon * 1.30 <= row[0] <= now - horizon * 0.75]
    if not candidates: return None
    earliest = min(candidates, key=lambda row: abs(row[0] - (now - horizon)))
    previous, current = int(earliest[1]), int(latest[1])
    delta = current - previous
    pct = round(delta / max(previous, 10) * 100, 1)
    return {'delta': delta, 'percent': pct, 'previous':previous,'current':current,
            'actual_minutes': round((latest[0] - earliest[0])/60)}

def evaluate(history, now=None):
    if not history:return {'score':0,'tier':'monitoring','windows':{w:None for w in WINDOWS}}
    now = now or history[-1][0]
    windows={w: window_growth(history,w,now) for w in WINDOWS}
    core = windows['15m'] or windows['1h'] or windows['6h']
    if not core: return {'score':0,'tier':'monitoring','windows':windows}
    recent=[row for row in history if row[0]>=now-3600]
    gains=[b[1]-a[1] for a,b in zip(recent,recent[1:])]
    positive=sum(x>0 for x in gains)
    rising=len(gains)>=2 and positive>=max(2,math.ceil(len(gains)*.55))
    gain=max(core['delta'],0); percent=max(core['percent'],0)
    score = min(100,round(min(38,percent*.17) + min(35,math.log1p(gain)*5.0)
        + (15 if rising else 0) + (12 if len(gains)>2 and gains[-1]>max(5,gains[0]*1.5) else 0)))
    tier='monitoring'
    if rising and gain>=25 and percent>=40:tier='scout'
    if rising and gain>=80 and percent>=90 and score>=55:tier='breakout'
    if rising and gain>=300 and percent>=180 and score>=75:tier='viral'
    return {'score':score,'tier':tier,'windows':windows}
