"""Encrypt the entire private monitoring state and browser data before committing to a PUBLIC repository.
No secret key, player history, watchlist, or webhook may be included in the public site.
"""
import base64
import json
import os
import secrets
import zlib
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def get_key():
    raw = os.environ.get('GAMESNIPER_STATE_KEY', '').strip()
    if not raw:
        raise RuntimeError('Missing GAMESNIPER_STATE_KEY GitHub Actions secret. Scanner disabled for safety.')
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise ValueError('GAMESNIPER_STATE_KEY must be base64-encoded 32 random bytes.') from exc
    if len(key) != 32:
        raise ValueError('GAMESNIPER_STATE_KEY must be 32 bytes after base64 decoding.')
    return key


def write_bundle(path, payload, key):
    raw = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(key).encrypt(nonce, zlib.compress(raw, 6), b'gamesniper-v1')
    data = {'version': 1, 'alg': 'AES-256-GCM+zlib',
            'nonce': base64.b64encode(nonce).decode('ascii'),
            'ciphertext': base64.b64encode(ciphertext).decode('ascii')}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, separators=(',', ':')), encoding='utf-8')
    temp.replace(path)


def read_bundle(path, key):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('version') != 1 or data.get('alg') != 'AES-256-GCM+zlib':
        raise ValueError('Unsupported encrypted state format; refusing to overwrite it.')
    raw = AESGCM(key).decrypt(base64.b64decode(data['nonce']),
                              base64.b64decode(data['ciphertext']), b'gamesniper-v1')
    return json.loads(zlib.decompress(raw))
