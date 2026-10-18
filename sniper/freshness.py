"""Strict date-based admission to the early-game radar.

'First observed' is NOT equivalent to game creation or Steam release.
Unknown dates are never silently treated as recent.
"""
import re
from datetime import datetime, timezone

_DATE_FORMATS = ('%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ',
                 '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d', '%b %d, %Y',
                 '%B %d, %Y', '%d %b, %Y', '%d %B, %Y', '%b %d %Y')


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = re.sub(r'\s+', ' ', value.strip())
    if value.lower() in ('coming soon', 'to be announced', 'tba', 'unannounced'):
        return None
    for fmt in _DATE_FORMATS:
        try:
            result = datetime.strptime(value, fmt)
            return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def days_old(game, now):
    date = parse_date(game.get('created_at'))
    return None if date is None else (now - date.timestamp()) / 86400


def recent(game, now, max_age_days):
    age = days_old(game, now)
    return age is not None and -1 <= age <= max_age_days


def breakout_candidate(game, now, cfg):
    limit = cfg.get('roblox_max_age_days', 30) if game.get('platform') == 'roblox' else cfg.get('steam_max_age_days', 30)
    return recent(game, now, float(limit))
