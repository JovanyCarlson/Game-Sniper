import asyncio
import base64
import hashlib
import hmac
import json
import unittest
from unittest.mock import patch,AsyncMock
from sniper.manual_send import selector_for, find_game, deliver
from sniper.engine import new_state


class FakeResponse:
    status_code=204
    def raise_for_status(self):pass

class FakeClient:
    def __init__(self):self.messages=[]
    async def post(self, url, json=None, timeout=None):
        self.messages.append((url,json))
        return FakeResponse()

class TestManualDiscord(unittest.TestCase):
    def setUp(self):
        self.key = bytes(range(32))
        self.state=new_state()
        self.state['games']['roblox:17']={'platform':'roblox','gid':'17','name':'Steal Eggs',
            'url':'https://www.roblox.com/games/501','players':123,'visits':800,
            'created_at':'2026-10-15','up_votes':20,'down_votes':5,'last_polled':120000,
            'history':[[115000,10],[120000,123]],
            'signal':{'tier':'scout','score':54,'windows':{'1h':None,'15m':None,'6h':None,'24h':None}}}
        self.sel = selector_for('roblox','17',self.key)

    def test_matches_webcrypto_hmac_sha256(self):
        expected=hmac.new(self.key,b'gamesniper:manual-send:v1:roblox:17',hashlib.sha256).hexdigest()
        self.assertEqual(self.sel,expected)
        self.assertEqual(len(self.sel),64)
        self.assertNotIn('17',self.sel)

    def test_unknown_selector_cannot_send_any_game(self):
        self.assertRaises(ValueError,find_game,self.state,'0'*64,self.key)
        for fake in ('steam:17','1','../config.json','f'*65,''):
            self.assertRaises(ValueError,find_game,self.state,fake,self.key)

    def test_owner_can_send_with_existing_secret_and_no_plaintext_input(self):
        fake=FakeClient()
        with patch('sniper.manual_send.sources.roblox_metrics',new=AsyncMock(return_value=([],[]))):
            payload=asyncio.run(deliver(self.sel, self.state, self.key,
                'https://discord.com/api/webhooks/123/fake-for-test',fake,now=120010))
        self.assertEqual(len(fake.messages),1)
        self.assertEqual(payload['embeds'][0]['title'],'Steal Eggs')
        self.assertIn('MANUALLY SENT',payload['embeds'][0]['description'])
        self.assertEqual(payload['embeds'][0]['url'],'https://www.roblox.com/games/501')
        self.assertNotIn('fake-for-test',json.dumps(payload))
        self.assertIn('800',str(payload['embeds'][0]['fields']))

    def test_rejects_missing_webhook_without_post(self):
        with self.assertRaises(RuntimeError):
            asyncio.run(deliver(self.sel,self.state,self.key,'wrong',FakeClient(),now=120010))

    def test_stale_sample_is_labeled_not_spoofed(self):
        fake=FakeClient()
        with patch('sniper.manual_send.sources.roblox_metrics',new=AsyncMock(return_value=([],[]))):
            payload=asyncio.run(deliver(self.sel,self.state,self.key,
                'https://discord.com/api/webhooks/123/fake-for-test',fake,now=130000))
        self.assertIn('Last valid sample',payload['embeds'][0]['footer']['text'])

if __name__=='__main__':unittest.main()
