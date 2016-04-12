import logging
from pprint import pprint as pp  # noqa

from jinja2 import Environment, FileSystemLoader

import tornado.log
import tornado.autoreload
import tornado.ioloop
import tornado.web
import tornado.httputil
from tornado.httpclient import AsyncHTTPClient
from tornado.options import options

from db_api import get_db_api
from resolver import Resolver
from cache import RedisCache
from handlers import (
    DBApiRequestHandler,
    TestView,
)

from settings import (
    PORT,
    DEBUG,
    CURL,
    DNS_RECORD_TTL,
    DB_API,
    JINJA,
    REDIS,
)


class NightpartyApplication(tornado.web.Application):
    def __init__(self, handlers=None):
        if not handlers:
            handlers = []

        AsyncHTTPClient.configure(
            "tornado.curl_httpclient.CurlAsyncHTTPClient",
            max_clients=CURL['MAX_CLIENTS'],
        )

        self.cache = RedisCache(**REDIS['CLIENT'])
        self.cache.initialize(**REDIS['TORNADO_CLIENT'])

        tornado.ioloop.IOLoop.instance().add_future(
            self.cache.run(),
            lambda future: future.result()
        )

        Api = get_db_api(is_cached=True)
        self.db_api = Api(
            DB_API['HOST'], DB_API['PORT'],
            http_client=AsyncHTTPClient(),
            resolver=Resolver(
                ttl=DNS_RECORD_TTL
            ),
            cache=self.cache,
            cache_key_ttl=DB_API['CACHE_KEY_TTL'],
            connect_timeout=CURL['CONNECT_TIMEOUT'],
            request_timeout=CURL['REQUEST_TIMEOUT'],
        )

        self.jinja = Environment(
            loader=FileSystemLoader(
                JINJA['TEMPLATE_ROOT']
            ),
            **JINJA['SETTINGS']
        )

        handlers += [
            (r'/db/(?P<api_path>.*)', DBApiRequestHandler),
        ]

        if DEBUG:
            handlers += [
                (r'/test/', TestView),
            ]

        config = dict(
            debug=DEBUG,
        )

        tornado.web.Application.__init__(self, handlers, **config)


def make_app(handlers=None):
    """ для тестов """
    return NightpartyApplication(handlers)


if __name__ == "__main__":
    if DEBUG:
        import os
        path = os.path.dirname(os.path.realpath(__file__))
        tornado.autoreload.start()
        for dir, _, files in os.walk(path + '/'):
            if not dir.startswith('.'):
                [tornado.autoreload.watch(dir + '/' + f) for f in files if not f.startswith('.')]

    options.parse_command_line()
    logging.debug('Nightparty!')

    application = NightpartyApplication()
    application.listen(PORT)

    tornado.ioloop.IOLoop.instance().start()
