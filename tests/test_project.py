import asyncio, tempfile, time, unittest
from unittest.mock import patch,AsyncMock
from sniper.scoring import evaluate,window_growth
from sniper.discord import build_embed
from sniper.engine import apply_metric,merge_candidates,new_state,pending_alerts,priority_select,qualify,to_public,run_once
from sniper.sources import discover_universes

SETTINGS={'alerts':{'primary_window':'1h','minimum_player_gain':35,'minimum_growth_percent':60,
'cooldown_minutes':120,'include_scout':True},'scan':{},'watchlist':{}}

class TestGameSniper(unittest.TestCase):
 def test_window_accuracy_and_insufficient_history(self):
  now=100_000
  h=[[now-1000,10],[now-600,30],[now-300,70],[now,150]]
  self.assertIsNone(window_growth(h,'1h',now))
  self.assertEqual(window_growth(h,'15m',now)['delta'],140)
 def test_breakout_score(self):
  h=[[100_000-1200,30],[100_000-900,45],[100_000-600,80],[100_000-300,150],[100_000,350]]
  sig=evaluate(h)
  self.assertIn(sig['tier'],('scout','breakout','viral'))
  self.assertGreater(sig['score'],40)
 def test_no_out_of_thin_air_data(self):
  state=new_state();merge_candidates(state,[{'platform':'roblox','gid':'42'}],1000)
  self.assertFalse(pending_alerts(state,SETTINGS,1000))
 def test_metric_and_history(self):
  state=new_state();metric={'platform':'roblox','gid':'42','players':12,'visits':100,'name':'Example'}
  apply_metric(state,metric,1000);apply_metric(state,{**metric,'players':19},1300)
  self.assertEqual(state['games']['roblox:42']['history'],[[1000,12],[1300,19]])
  self.assertEqual(state['games']['roblox:42']['visits'],100)
 def test_candidate_guard(self):
  state=new_state();merge_candidates(state,[{'platform':'roblox','gid':'NOT_ID'}, {'platform':'steam','gid':'91'}],100)
  self.assertIn('steam:91',state['games']);self.assertNotIn('roblox:NOT_ID',state['games'])
 def test_votes_discovery(self):
  ids=discover_universes({'content':[{'universeId':123,'name':'Test'},{'universeId':None,'name':'wrong'}]})
  self.assertEqual(ids[0]['gid'],'123');self.assertEqual(len(ids),1)
 def test_steam_review_embed(self):
  g={'platform':'steam','gid':'123','name':'Alpha @everyone','url':'https://store.steampowered.com/app/123/',
     'players':280,'created_at':'Oct 15, 2026','positive_reviews':90,'negative_reviews':10}
  sig={'tier':'breakout','score':80,'windows':{'15m':{'delta':10,'percent':5},'1h':{'delta':100,'percent':55},'6h':None,'24h':None}}
  d=build_embed(g,sig,'1h',100000)
  embed=d['embeds'][0];self.assertEqual(embed['url'],g['url'])
  self.assertNotIn('@everyone',embed['title'])
  self.assertIn('90.0% positive',str(embed['fields']))
  self.assertIn('Not public on Steam',str(embed['fields']))
  self.assertEqual(d['allowed_mentions']['parse'],[])
 def test_roblox_likes_embed(self):
  g={'platform':'roblox','gid':'1','name':'Beta','url':'https://www.roblox.com/games/2',
    'players':55,'visits':1345,'created_at':'2026-01-01','up_votes':80,'down_votes':20}
  sig={'tier':'scout','score':49,'windows':{'15m':None,'1h':None,'6h':None,'24h':None}}
  out=build_embed(g,sig,'15m',1000)
  self.assertIn('80.0% 👍',str(out))
  self.assertIn('1,345',str(out))
 def test_alert_cooldown_and_realert_on_escalation(self):
  state=new_state();state['games']={'steam:10':{'platform':'steam','gid':'10','players':180,'last_polled':10000,
  'signal':{'score':80,'tier':'breakout','windows':{'15m':{'delta':95,'percent':140}}}}}
  self.assertEqual(len(pending_alerts(state,SETTINGS,10000)),1)
  state['games']['steam:10']['last_alert']={'time':10000,'tier':'breakout'}
  self.assertEqual(len(pending_alerts(state,SETTINGS,10100)),0)
  state['games']['steam:10']['signal']['tier']='viral'
  self.assertEqual(len(pending_alerts(state,SETTINGS,10100)),1)
 def test_dashboard_safe_state(self):
  state=new_state();state['meta']['last_scan']=1000
  self.assertEqual(to_public(state,1000)['status']['tracked'],0)
 def test_integrated_scan_uses_real_results_without_demo(self):
  state=new_state()
  config={'alerts':SETTINGS['alerts'],'scan':{'roblox_limit':4,'steam_limit':4,'steam_details_per_cycle':0},
          'watchlist':{'roblox_universe_ids':['42'],'steam_app_ids':['730']}}
  samples=[{'platform':'roblox','gid':'42','name':'Public Game','players':80,'visits':456,'created_at':'2026-09-01',
             'url':'https://www.roblox.com/games/20'},
           {'platform':'steam','gid':'730','name':'Example Steam','players':90,
             'url':'https://store.steampowered.com/app/730/'}]
  class Client:
   async def aclose(self):pass
  with patch('sniper.engine.sources.roblox_metrics',new=AsyncMock(return_value=([samples[0]],[]))), \
       patch('sniper.engine.sources.steam_metrics',new=AsyncMock(return_value=([samples[1]],[]))):
   new_state_obj,public=asyncio.run(run_once(config=config,state=state,client=Client(),now=1200,discover=False))
  self.assertEqual(public['mode'],'live')
  self.assertEqual(public['status']['successful_games'],2)
  self.assertEqual(len(public['games']),2)
  self.assertIsNone(public['games'][0]['signal']['windows']['1h'])
  self.assertEqual(new_state_obj['games']['roblox:42']['visits'],456)
 def test_rotation_reaches_old_games(self):
  games=[{'gid':str(i),'last_polled':i*100,'signal':{'score':0}} for i in range(25)]
  chosen=priority_select(games,set(),5,1,10000)
  self.assertEqual(chosen[0]['gid'],'0')

if __name__=='__main__':unittest.main()
