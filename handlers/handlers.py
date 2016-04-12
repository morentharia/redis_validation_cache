import logging
from pprint import pprint as pp  # noqa

import json

from tornado import gen
from tornado.web import (
    HTTPError,
    RequestHandler
)

from .tools import (
    JinjaTemplateMixin,
    CacheMixin,
)


class DBApiRequestHandler(RequestHandler):
    SUPPORTED_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']

    def _ok(self, data):
        self.set_status(200)
        self.write(
            json.dumps(
                {
                    'status': 'ok',
                    'data': data,
                }
            )
        )

    def _error(self, error_message):
        logging.error(error_message)
        self.set_status(400)
        self.set_header('Content-Type', 'application/json; charset=UTF-8')
        self.write(
            json.dumps(
                {
                    'status': 'fail',
                    'data': error_message,
                }
            )
        )

    @gen.coroutine
    def prepare(self):
        try:
            # print(type(self.request))
            # print(self.request.query)

            api_path = self.path_kwargs.get('api_path', '')
            if not api_path.startswith('/'):
                api_path = '/' + api_path

            params = {k: self.get_argument(k) for k in self.request.arguments}

            data = {}
            if self.request.body:
                data = json.loads(self.request.body.decode())

        except ValueError:
            self._error({"message": "invalid JSON"})
            self.finish()
            return

        is_ok, res = yield self.application.db_api.request(
            self.request.method,
            path=api_path,
            params=params,
            data=data,
        )
        if not is_ok:
            self._error(res)
            self.finish()
            return

        response = res
        if response['code'] not in [200, 201]:
            self._error(response['data'])
            self.finish()
            return

        self.set_status(response['code'])
        for k, v in response['headers']:
            self.set_header(k, v)
        self._ok(response['data'])
        self.finish()

    def get(self, *args, **kwargs):
        pass

    def post(self, *args, **kwargs):
        pass

    def put(self, *args, **kwargs):
        pass

    def patch(self, *args, **kwargs):
        pass

    def delete(self, *args, **kwargs):
        pass


class TestView(
    CacheMixin,
    JinjaTemplateMixin,
    RequestHandler
):

    @gen.coroutine
    def get(self):
        params = {k: self.get_argument(k) for k in self.request.arguments}

        is_ok, res = yield self.application.db_api.get(
            '/api/events/',
            params=params,
            # data=[],
        )
        if not is_ok:
            raise HTTPError(404)

        self.render(
            'test.html',
            name='zzzzdddd',
            places=res['data'],
        )
        self.write('закэшируй меня целиком')
