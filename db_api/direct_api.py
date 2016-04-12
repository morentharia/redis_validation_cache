from pprint import pprint as pp  # noqa
from random import choice
from urllib.parse import urlencode
import logging

import json

from tornado import gen
from tornado.platform.caresresolver import CaresResolver
from tornado.httpclient import HTTPRequest
from tornado.httpclient import AsyncHTTPClient

from . import DBApiError


class DBApiDirect:
    """
        RESTApi к базе без кэша
    """
    # TODO: добавь суюда сахар aля get_palces get_cities
    def __init__(self, host, port,
                 resolver=None,
                 http_client=None,
                 connect_timeout=0,
                 request_timeout=0,
                 **kwargs):
        self.host = host
        self.port = port
        self._connect_timeout = connect_timeout
        self._request_timeout = request_timeout

        self._http_client = http_client
        if not self._http_client:
            self._http_client = AsyncHTTPClient()

        self._resolver = resolver
        if not self._resolver:
            self._resolver = CaresResolver()

    @gen.coroutine
    def _resolve(self, host, port):
        try:
            addresses = yield self._resolver.resolve(host, port)
            if not addresses:
                raise DBApiError('empty addresses list for %s:%s' % (host, port))
        except Exception as e:
            raise DBApiError(e)

        return choice(addresses)[1]  # noqa

    def _create_http_request(self, method, host, port, path,
                             params=None, data=None, **kwargs):

        url = 'http://{host}:{port}{uri}'.format(host=host, port=port, uri=path)

        if params and isinstance(params, dict):
            url += '?' + urlencode(params)

        request = HTTPRequest(
            method=method,
            url=url,
            allow_nonstandard_methods=True,
            connect_timeout=self._connect_timeout,
            request_timeout=self._request_timeout,
            **kwargs
        )

        if data and method in ['POST', 'PUT', 'PATCH']:
            try:
                request.body = json.dumps(data)
            except TypeError as e:
                logging.error(str(e))
                raise DBApiError(e)

        return request

    def _check_request(self, request):
        if request.method not in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']:
            raise DBApiError('Disallowed method %s' % request.method)

    @staticmethod
    def _format_output(response):
        result = {}
        try:
            result = {
                'code': int(response.code),
                'headers': list(response.headers.get_all()),
                'data': {},
            }
            if response.body:
                result['data'] = json.loads(response.body.decode())
        except Exception as e:
            result = {
                'code': 400,
                'headers': [],
                'data': {
                    'message': str(e),
                },
            }
        return result

    @gen.coroutine
    def _request(self, host, port, method, path,
                 params=None, data=None, **kwargs):

        request = self._create_http_request(
            method,
            host,
            port,
            path,
            params=params,
            data=data,
            headers={'Content-Type': 'application/json; charset=UTF-8'},
            **kwargs
        )
        self._check_request(request)

        http_response = yield self._http_client.fetch(
            request,
            raise_error=False,
        )

        data = self._format_output(http_response)
        return data  # noqa

    @gen.coroutine
    def request(self, method, *args, **kwargs):
        try:
            host, port = yield self._resolve(self.host, self.port)

            result = yield self._request(host, port, method, *args, **kwargs)

        except DBApiError as e:
            return False, str(e)  # noqa

        except Exception as e:
            logging.error("error %s", str(e))
            raise

        return True, result  # noqa

    @gen.coroutine
    def get(self, *args, **kwargs):
        res = yield self.request('GET', *args, **kwargs)
        return res  # noqa

    @gen.coroutine
    def post(self, *args, **kwargs):
        res = yield self.request('POST', *args, **kwargs)
        return res  # noqa

    @gen.coroutine
    def put(self, *args, **kwargs):
        res = yield self.request('PUT', *args, **kwargs)
        return res  # noqa

    @gen.coroutine
    def patch(self, *args, **kwargs):
        res = yield self.request('PATCH', *args, **kwargs)
        return res  # noqa

    @gen.coroutine
    def delete(self, *args, **kwargs):
        res = yield self.request('DELETE', *args, **kwargs)
        return res  # noqa
