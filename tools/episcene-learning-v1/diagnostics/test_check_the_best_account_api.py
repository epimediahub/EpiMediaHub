#!/usr/bin/env python3
"""No-network tests for allowlisted Xtream metadata response and privacy."""
from contextlib import contextmanager
import json
import unittest
from unittest.mock import patch
import check_the_best_account_api as m

class CheckMetadata(unittest.TestCase):
    def _fake_reply(self, body):
        class Reply:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return None
            def read(self,limit):return body[:limit]
        class Opener:
            def open(self,*args,**kwargs):return Reply()
        class Analysis:
            class ProviderFailure(ValueError):pass
            @staticmethod
            @contextmanager
            def _provider_proxy_local(source,busy):
                yield 'http://127.0.0.1:30123/redacted'
        return Analysis,Opener()

    def test_authenticated_active_with_one_busy_connection(self):
        body=json.dumps({'user_info':{
            'auth':1,'status':'Active','active_cons':'1',
            'max_connections':'1','username':'PRIVATE_USER','password':'PRIVATE_PASSWORD'}}).encode()
        analysis,opener=self._fake_reply(body)
        with patch('urllib.request.build_opener',return_value=opener):
            result=m.request_account(analysis,'PRIVATE_URL_WITH_CREDENTIALS')
        self.assertEqual(result,{'api_result':'XTREAM_ACCOUNT_RESPONSE','auth':'ACCEPTED',
                                 'account_status':'ACTIVE','active_connections':1,
                                 'maximum_connections':1})
        for secret in ('PRIVATE_USER','PRIVATE_PASSWORD','PRIVATE_URL_WITH_CREDENTIALS'):
            self.assertNotIn(secret,str(result))

    def test_invalid_json_does_not_leak(self):
        analysis,opener=self._fake_reply(b'PRIVATE_BAD_RESPONSE')
        with patch('urllib.request.build_opener',return_value=opener):
            result=m.request_account(analysis,'PRIVATE_URL')
        self.assertEqual(result,{'api_result':'HTTP_200_NOT_STANDARD_XTREAM_ACCOUNT_JSON'})
        self.assertNotIn('PRIVATE',str(result))

    def test_bounded_number(self):
        analysis,opener=self._fake_reply(json.dumps({'user_info':{
            'auth':'0','status':'Banned','active_cons':'987654',
            'max_connections':'2'}}).encode())
        with patch('urllib.request.build_opener',return_value=opener):
            result=m.request_account(analysis,'PRIVATE_URL')
        self.assertEqual(result['auth'],'NOT_ACCEPTED')
        self.assertEqual(result['account_status'],'BANNED')
        self.assertEqual(result['active_connections'],'NOT_REPORTED')

if __name__=='__main__':unittest.main()
