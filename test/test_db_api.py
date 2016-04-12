# import tornado
from urllib.parse import urlencode
from pprint import pprint as pp  # noqa
from mock import Mock, patch
from io import BytesIO
from collections import OrderedDict

import json

from tornado.httpclient import HTTPResponse, HTTPRequest
from tornado import gen
from tornado.testing import AsyncHTTPTestCase
from tornado.testing import gen_test
from tornado.web import RequestHandler
from tornado.httputil import HTTPHeaders


from handlers.tools import (
    JinjaTemplateMixin,
    CacheMixin,
)


import main


class TestCache(dict):
    def get(self, key):
        return super().get(key).encode()

    def set(self, key, value, key_ttl):
        self[key] = value

    def delete(self, key):
        del self[key]

    def exists(self, key):
        return key in self


class CacheDBApiTest(AsyncHTTPTestCase):

    def get_app(self):

        class TestMeView(
            CacheMixin,
            JinjaTemplateMixin,
            RequestHandler
        ):

            @gen.coroutine
            def get(self):
                self.write('chunk-1*')
                self.write('chunk-2*')
                self.write('chunk-3')

        self.application = main.make_app(
            [
                (r'/testme/', TestMeView),
            ]
        )
        return self.application

    @gen_test
    def test_cache_mixin_key_exists(self):
        url = self.get_url('/testme/')
        url += '?' + urlencode(
            dict(
                ordeding='-slug',
                city='moscow',
                another_filter='420',
            )
        )
        self.application.cache = Mock(
            options={
            },
            **{
                'exists.return_value': True,
                'get.return_value': 'cached response',
            }
        )
        response = yield self.http_client.fetch(url, method='GET')
        self.assertEqual(response.body, b'cached response')

    @gen_test
    def test_cache_mixin_key_not_exists(self):
        url = self.get_url('/testme/')
        url += '?' + urlencode(
            dict(
                ordeding='-slug',
                city='moscow',
                another_filter='420',
            )
        )

        self.application.cache = Mock(
            options={
            },
            **{
                'exists.return_value': False,
                'get.return_value': 'cached response',
                'set.return_value': True,
            }
        )

        response = yield self.http_client.fetch(url, method='GET')
        self.assertEqual(response.body, b'chunk-1*chunk-2*chunk-3')
        self.assertEqual(self.application.cache.set.called, True)

    @gen_test
    def test_db_api_not_cached_ok(self):
        url = self.get_url('/db/api/places/')
        url += '?' + urlencode(
            dict(
                ordeding='-slug',
                city='moscow',
            )
        )

        self.application.db_api.cache = Mock()
        self.application.db_api.cache.exists.return_value = False

        @gen.coroutine
        def mock_fetch(request, *args, **kwargs):
            buffer = BytesIO(
                b'''
                {
                    "not_cached": "test"
                }
                '''
            )
            response = HTTPResponse(request, 200, None, buffer)
            return response

        self.application.db_api._http_client = Mock()
        self.application.db_api._http_client.fetch.side_effect = mock_fetch

        request = HTTPRequest(url, method='GET')

        response = yield self.http_client.fetch(request, raise_error=False)
        self.assertEqual(json.loads(response.body.decode())['data'], {"not_cached": "test"})
        self.assertEqual(self.application.db_api.cache.set.called, True)

    @gen_test
    def test_db_api_cached_ok(self):
        url = self.get_url('/db/api/places/')
        params = OrderedDict()
        params['ordeding'] = '-slug'
        params['city'] = 'moscow'
        url += '?' + urlencode(params)

        self.application.db_api.cache = TestCache()

        @gen.coroutine
        def mock_db_fetch(request, *args, **kwargs):
            buffer = BytesIO(
                b'''
                {
                    "not_cached": "test"
                }
                '''
            )
            response = HTTPResponse(request, 200, None, buffer)
            return response
        self.application.db_api._http_client = Mock()
        self.application.db_api._http_client.fetch.side_effect = mock_db_fetch

        mock_time = Mock()
        mock_time.return_value = 111.0
        with patch('db_api.cached_api.time', mock_time):
            request = HTTPRequest(url, method='GET')
            response = yield self.http_client.fetch(request, raise_error=False)

        cached_request = self.application.db_api.cache['/api/places/||city=moscow&ordeding=-slug']
        cached_request = json.loads(cached_request)
        self.assertDictEqual(
            cached_request['__meta__'],
            {'created': 111.0, 'tags': ['places']},
        )
        self.assertDictEqual(json.loads(response.body.decode())['data'], {"not_cached": "test"})

        request = HTTPRequest(url, method='GET')
        response = yield self.http_client.fetch(request, raise_error=False)
        self.assertDictEqual(json.loads(response.body.decode())['data'], {"not_cached": "test"})

        mock_time = Mock()
        mock_time.return_value = 222
        with patch('db_api.cached_api.time', mock_time):

            request = HTTPRequest(
                method='POST',
                url=self.get_url('/db/api/places/'),
                body=str('{"haha":1}'),
            )
            response = yield self.http_client.fetch(request, raise_error=False)

        self.assertDictEqual(
            self.application.db_api.cache_meta_data.forget_everything_before,
            {'places': 222}
        )

        @gen.coroutine
        def mock_db_fetch_2(request, *args, **kwargs):
            # print(request.method, request.url)
            buffer = BytesIO(
                b'''
                {
                    "not_cached": "after POST"
                }
                '''
            )
            response = HTTPResponse(request, 200, None, buffer)
            return response
        self.application.db_api._http_client.fetch.side_effect = mock_db_fetch_2

        request = HTTPRequest(url, method='GET')
        response = yield self.http_client.fetch(request, raise_error=False)
        self.assertDictEqual(json.loads(response.body.decode())['data'], {"not_cached": "after POST"})

    @gen_test
    def test_invalid_json(self):
        url = self.get_url('/db/api/places/')
        params = OrderedDict()
        params['ordeding'] = '-slug'
        params['city'] = 'moscow'
        params['another_filter'] = 'invalid_json',
        url += '?' + urlencode(params)

        request = HTTPRequest(
            method='POST',
            url=url,
            headers={'Content-Type': 'application/json; charset=UTF-8'},
            body='''{invalid json}'''.encode(),
        )
        response = yield self.http_client.fetch(request, raise_error=False)
        self.assertEqual(json.loads(response.body.decode())['status'], 'fail')

    @gen_test
    def test_valid_json_but_error_fields(self):
        url = self.get_url('/db/api/places/')
        params = OrderedDict()
        params['ordeding'] = '-slug'
        params['city'] = 'moscow'
        params['another_filter'] = 'invalid_json',
        url += '?' + urlencode(params)

        @gen.coroutine
        def mock_db_fetch(request, *args, **kwargs):
            buffer = BytesIO(
                b'''
                    {
                        "city": ["This field is required."],
                        "name": ["This field is required."]
                    }
                '''
            )
            response = HTTPResponse(
                request,
                400,
                HTTPHeaders({'Content-Type': 'application/json; charset=UTF-8'}),
                buffer,
            )
            return response
        self.application.db_api._http_client = Mock()
        self.application.db_api._http_client.fetch.side_effect = mock_db_fetch

        request = HTTPRequest(
            method='POST',
            url=url,
            headers={'Content-Type': 'application/json; charset=UTF-8'},
            body=''' {  } ''',
        )
        response = yield self.http_client.fetch(request, raise_error=False)

        self.assertEqual(response.code, 400)
        self.assertEqual(json.loads(response.body.decode())['status'], 'fail')
        self.assertEqual(
            json.loads(response.body.decode())['data'],
            {
                "city": ["This field is required."],
                "name": ["This field is required."]
            }
        )
