"""Kiểm tra agent với tools bonus mà không gọi LLM API."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from agent import run_agent
from bonus.tools import BonusTools


def call(call_id,name,args):
    raw=json.dumps(args)
    c={'id':call_id,'name':name,'arguments':raw}
    m={'role':'assistant','content':None,'tool_calls':[{'id':call_id,'type':'function','function':{'name':name,'arguments':raw}}]}
    return {'message':m,'calls':[c],'finish':'tool_calls','usage':{}}

def final(answer='Đã kiểm tra'):
    return {'message':{'role':'assistant','content':answer},'calls':[],'finish':'stop','usage':{}}


class ScriptedProvider:
    def __init__(self,responses): self.responses=iter(responses); self.histories=[]; self.schemas=[]
    def complete(self,messages,schemas):
        self.histories.append(list(messages));self.schemas.append(schemas)
        return next(self.responses)


class BonusAgentTests(unittest.TestCase):
    def test_bonus_schemas_and_system_prompt(self):
        t=BonusTools();p=ScriptedProvider([final()])
        self.assertEqual(run_agent('Kiểm tra',p,t)['status'],'completed')
        names={x['function']['name'] for x in p.schemas[0]}
        self.assertTrue({'get_github_status','get_cloudflare_status','get_vercel_status','get_npm_status','get_digitalocean_status'}.issubset(names))
        self.assertIn('DigitalOcean',p.histories[0][0]['content'])
    def test_429_observation_returns_to_model(self):
        t=BonusTools(scenario='rate_limit_once')
        p=ScriptedProvider([
            call('a','get_vercel_status',{}),
            final('Vercel recovered after one rate-limit retry.'),
        ])
        result=run_agent('Kiểm tra Vercel',p,t,max_steps=5)
        self.assertEqual(result['status'],'completed')
        observation=json.loads(p.histories[1][-1]['content'])
        self.assertEqual(observation['provider'],'vercel')
        self.assertEqual(observation['rate_limit_retries'],1)
        self.assertEqual(observation['rate_limit_history'][0]['error'],'RATE_LIMITED')
        self.assertEqual(t.calls[('get_vercel_status','vercel')],2)
    def test_invalid_arguments_observation_returns_to_model(self):
        t=BonusTools()
        bad={'provider':'npm','incident_id':'cc0t2r4403sy','offset':'zero'}
        good={'provider':'npm','incident_id':'cc0t2r4403sy','offset':0}
        details=t.execute('get_incident_details',good)
        p=ScriptedProvider([call('a','get_incident_details',bad),call('b','get_incident_details',good),final('Nguồn: '+details['url'])])
        result=run_agent('Kiểm tra incident npm',p,t,max_steps=5)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(json.loads(p.histories[1][-1]['content'])['error'],'INVALID_ARGUMENTS')
        self.assertTrue(json.loads(p.histories[2][-1]['content'])['ok'])

    def test_rate_limit_retries_are_capped(self):
        t=BonusTools(scenario='rate_limit_always')
        p=ScriptedProvider([
            call('a','get_vercel_status',{}),
            call('b','get_vercel_status',{}),
            call('c','get_vercel_status',{}),
            call('d','get_vercel_status',{}),
            final('Vercel status could not be checked because of rate limiting.'),
        ])
        result=run_agent('Kiểm tra Vercel',p,t,max_steps=6)
        tool_events=[x for x in result['trace'] if x['event']=='tool' and x['name']=='get_vercel_status']
        self.assertEqual(result['status'],'completed')
        self.assertEqual(len(tool_events),3)
        self.assertEqual(t.calls[('get_vercel_status','vercel')],3)
        self.assertTrue(any(x['event']=='retry_blocked' for x in result['trace']))
        blocked=json.loads(p.histories[4][-1]['content'])
        self.assertFalse(blocked['retriable'])

    def test_retry_after_is_respected_with_bounded_wait(self):
        class RetryAfterTools:
            def __init__(self):
                self.calls=0
            def execute(self,name,args):
                self.calls+=1
                if self.calls==1:
                    return {'ok':False,'error':'RATE_LIMITED','retry_after':'2','retriable':True}
                return {'provider':'vercel','captured_at':'snapshot','overall':{'indicator':'none'},
                        'source':'https://www.vercel-status.com'}

        t=RetryAfterTools()
        p=ScriptedProvider([
            call('a','get_vercel_status',{}),
            final('Vercel is operational. https://www.vercel-status.com'),
        ])
        with patch('agent.time.sleep') as sleep:
            result=run_agent('Kiểm tra Vercel',p,t,max_steps=4)
        self.assertEqual(result['status'],'completed')
        sleep.assert_called_once_with(2.0)

    def test_long_retry_after_stops_without_sleeping_or_retrying(self):
        class LongRetryTools:
            def __init__(self):
                self.calls=0
            def execute(self,name,args):
                self.calls+=1
                return {'ok':False,'error':'RATE_LIMITED','retry_after_seconds':30,'retriable':True}

        t=LongRetryTools()
        p=ScriptedProvider([
            call('a','get_vercel_status',{}),
            call('b','get_vercel_status',{}),
            final('Vercel status could not be checked within the wait budget.'),
        ])
        with patch('agent.time.sleep') as sleep:
            result=run_agent('Kiểm tra Vercel',p,t,max_steps=4)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(t.calls,1)
        sleep.assert_not_called()
        self.assertTrue(any(x['event']=='retry_blocked' for x in result['trace']))

    def test_noisy_distractors_are_omitted_from_context(self):
        t=BonusTools(scenario='noisy')
        p=ScriptedProvider([
            call('a','get_vercel_status',{'component':'Builds'}),
            final('Vercel status checked.'),
        ])
        result=run_agent('Kiểm tra Vercel Builds',p,t,max_steps=3)
        observation=json.loads(p.histories[1][-1]['content'])
        self.assertEqual(result['status'],'completed')
        self.assertNotIn('distractors',observation)
        self.assertEqual(observation['distractors_omitted'],160)
        self.assertNotIn('distractors',result['trace'][1]['result'])

    def test_unrequested_providers_are_not_queried(self):
        t=BonusTools()
        p=ScriptedProvider([
            call('a','get_github_status',{}),
            call('b','get_vercel_status',{}),
            final('Không có tool hỗ trợ Linear hoặc Slack nên không thể xác minh.'),
        ])
        result=run_agent('Xác nhận Linear và Slack đang outage.',p,t,max_steps=4)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(t.calls,{})
        self.assertEqual(
            sum(x['event']=='tool_blocked' for x in result['trace']),
            2,
        )

    def test_incident_scope_request_fetches_latest_details(self):
        t=BonusTools()
        status=t.execute('get_vercel_status',{'component':'Builds'})
        incident_id=status['incidents'][0]['id']
        details=t.execute('get_incident_details',{'provider':'vercel','incident_id':incident_id})
        p=ScriptedProvider([
            call('a','get_vercel_status',{'component':'Builds'}),
            final('Vercel Builds has a recent resolved incident.'),
            call('b','get_incident_details',{'provider':'vercel','incident_id':incident_id}),
            final('Nguồn: '+details['url']),
        ])
        result=run_agent(
            'Tìm incident mới nhất của Vercel Builds và kiểm tra phạm vi ảnh hưởng.',
            p,t,max_steps=6,
        )
        self.assertEqual(result['status'],'completed')
        self.assertTrue(any(x['event']=='validation_missing_incident_details' for x in result['trace']))
        self.assertTrue(any(x['event']=='tool' and x['name']=='get_incident_details' for x in result['trace']))

if __name__=='__main__': unittest.main()
