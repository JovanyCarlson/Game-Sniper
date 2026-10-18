"""Private Discord delivery for an owner-selected game from the encrypted dashboard.

The workflow input is an opaque HMAC selector, NEVER the game name, id, URL,
Discord webhook or encryption key. Only records already in encrypted state can
be sent. This prevents the public GitHub Actions log from revealing picks.
"""
import asyncio
import hashlib
import hmac
import os
import re
import time
import httpx
from . import sources
from .privacy import get_key
from .engine import load_state, apply_metric, load_config
from .discord import build_embed

DOMAIN = b'gamesniper:manual-send:v1:'

def selector_for(platform, gid, key):
    if platform not in ('roblox', 'steam') or not str(gid).isdigit():
        raise ValueError('Invalid game identity')
    return hmac.new(key, DOMAIN + (platform + ':' + str(gid)).encode('ascii'), hashlib.sha256).hexdigest()

def find_game(state, selector, key):
    if not re.fullmatch(r'[0-9a-f]{64}', selector or ''):
        raise ValueError('Invalid opaque game selector')
    for game in state.get('games', {}).values():
        if hmac.compare_digest(selector_for(game['platform'], game['gid'], key), selector):
            if not game.get('last_polled'):
                raise ValueError('Selected game has never been sampled')
            return game
    raise ValueError('Game not found in private monitoring history')

async def deliver(selector, state=None, key=None, webhook=None, client=None, now=None):
    key = key if key is not None else get_key()
    state = state if state is not None else load_state()
    webhook = webhook if webhook is not None else os.environ.get('DISCORD_WEBHOOK_URL', '').strip()
    if not webhook.startswith('https://discord.com/api/webhooks/') and not webhook.startswith('https://discordapp.com/api/webhooks/'):
        raise RuntimeError('Discord webhook secret missing or invalid')
    game = find_game(state, selector, key)
    now = int(now or time.time())
    own_client = client is None
    client = client or httpx.AsyncClient(headers=sources.HEADERS, timeout=sources.TIMEOUT)
    try:
        try:
            if game['platform'] == 'roblox':
                samples, issues = await sources.roblox_metrics(client, [game['gid']])
            else:
                samples, issues = await sources.steam_metrics(client, [game])
            if samples:
                # Use a temporary copy; do not commit potentially racing data.
                import copy
                temp = copy.deepcopy(state)
                fresh = apply_metric(temp, samples[0], now)
                game = fresh
        except (httpx.HTTPError, ValueError, KeyError):
            pass  # Clearly mark stale readings below instead of inventing values.
        primary = load_config()['alerts'].get('primary_window', '1h')
        signal = game.get('signal') or {'tier': 'monitoring', 'score': 0, 'windows': {}}
        payload = build_embed(game, signal, primary, now)
        embed = payload['embeds'][0]
        embed['description'] = '**MANUALLY SENT FROM YOUR DASHBOARD**\n' + embed['description']
        sampled = game.get('last_polled') or 0
        freshness = 'Refreshed for this message' if now - sampled < 180 else f'Last valid sample {int((now-sampled)/60)} minutes ago'
        embed['footer']['text'] = 'GameSniper • ' + freshness + ' • Growth reflects stored samples'
        response = await client.post(webhook, json=payload, timeout=12)
        response.raise_for_status()
        return payload
    finally:
        if own_client: await client.aclose()

def main():
    selector = os.environ.get('GAME_SELECTOR', '').strip().lower()
    # Do not echo private game identity or webhook in public workflow logs.
    asyncio.run(deliver(selector))
    print('Manual GameSniper Discord delivery completed.')

if __name__ == '__main__':
    main()
