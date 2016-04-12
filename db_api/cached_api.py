import logging
from pprint import pprint as pp  # noqa
from io import BytesIO
from time import time
from collections import OrderedDict
from urllib.parse import (
    urlparse,
    parse_qsl,
    urlencode,
)

import json

from tornado.httpclient import HTTPRequest, HTTPResponse
from tornado.httputil import HTTPHeaders
from tornado import gen

from . import DBApiDirect


class CacheMetaDataValidator:
    """
        Каждой записи и кэш добавляем метадату в которую пишем время
        создания и тэги

        data['__meta__'] = {
            'created': float(time()),
            'tags': tags,
        }

        тэги в или группы или типы записи, генерим пока только из url
        зачем это нужно:

        если у нас GET запрос:

        GET localhost:8888/db/api/events/fkfk/places/dkd

        то с помощью  _get_tags_from_request(self, request)
        получаем список тэгов ['events']
        и записываем response вметсе с метадатой в кэш

        ##############################################################
        # request('GET localhost:8888/db/api/events/')               #
        #                     |                                      #
        #                     V                                      #
        # response('GET localhost:8888/db/api/events/')              #
        # create: "12:00"                                            #
        # tags: ['events']                                           #
        #                     |                                      #
        #                     V                                      #
        #                   CACHE                                    #
        ##############################################################

        через некоторое время приходит запрос

        POST localhost:8888/db/api/events/fkfk/places/dkd
        получаем список тэгов ['events', 'places']

        так как POST меняет что то в базе, то
        for tag in ['events', 'places']:
            self.forget_it(tags)

        в dict self.forget_everything_before будет записанно


        ##############################################################
        # request(POST localhost:8888/db/api/events/fkfk/places/dkd) #
        # tags: ['events', 'places']                                 #
        # create: 13:00                                              #
        #             |                                              #
        #             V                                              #
        # self.forget_everything_before = {                          #
        #     'events': '13:00'                                      #
        #     'places': '13:00'                                      #
        # }                                                          #
        ##############################################################

        снова GET запрос

        ###############################################################
        # request('GET localhost:8888/db/api/events/')                #
        #                     |                                       #
        #                     V                                       #
        #                   CACHE                                     #
        #                     |                                       #
        #                     V                                       #
        # response('GET localhost:8888/db/api/events/')               #
        # create: "12:00"                                             #
        # tags: ['events']                                            #
        ###############################################################

        проверяем метаданные

        self.forget_everything_before = {
            'events': '13:00'
            'places': '13:00'
        }

        все записи с тэгом 'events' < '13:00' надо забыть

        create: "12:00" => считаем запись не валидной

        перезапрашиваем базу
    """

    URL_TAGS = [
        'events',
        'places',
        'tag',
    ]

    def __init__(self):
        self.forget_everything_before = {
        }

    def _get_tags_from_request(self, request):
        tags = []

        url_path = urlparse(request.url).path
        url_path_list = url_path.split('/')

        for tag in self.URL_TAGS:
            if tag in url_path_list:
                tags.append(tag)

        return tags

    def create(self, data, response):
        tags = self._get_tags_from_request(response.request)

        data['__meta__'] = {
            'created': float(time()),
            'tags': tags,
        }

    def is_valid(self, data):
        try:
            cache_value_created = float(data['__meta__']['created'])
            tags = data['__meta__']['tags']
        except KeyError:
            return False

        for tag in tags:
            if cache_value_created <= self.forget_everything_before.get(tag, 0):
                return False

        return True

    def forget_it(self, tags):
        for tag in tags:
            self.forget_everything_before[tag] = time()

    def process_request(self, request):
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            tags = self._get_tags_from_request(request)
            self.forget_it(tags)


class DBApiCached(DBApiDirect):
    """
        Добавляет кэширование к DBApiDirect
    """

    def __init__(self, *args, **kwargs):
        self.cache = kwargs.pop('cache', None)
        if self.cache is None:
            raise TypeError('cache is required parameter for %s' % self.__class__)

        self.cache_key_ttl = kwargs.pop('cache_key_ttl', 3)

        self.cache_meta_data = CacheMetaDataValidator()

        super().__init__(*args, **kwargs)

    @staticmethod
    def _generate_cache_key(request):
        res = urlparse(request.url)
        q = parse_qsl(res.query)
        q.sort()
        query = urlencode(OrderedDict(q))

        key = '||'.join([
            # request.method,
            res.path,
            query,
        ])
        return key

    def _serialize_to_cache(self, response):
        data = {}
        self.cache_meta_data.create(data, response)

        data['url'] = response.request.url
        data['code'] = response.code
        data['headers'] = list(response.headers.get_all())
        data['body'] = response.body.decode()

        return json.dumps(data)

    def _deserialize_from_cache(self, value):
        data = json.loads(value.decode())

        if not self.cache_meta_data.is_valid(data):
            logging.debug('cache is expired!')
            return None

        try:
            headers = HTTPHeaders()
            for k, v in data['headers']:
                headers.add(k, v)

            response = HTTPResponse(
                HTTPRequest(url=data['url']),
                int(data['code']),
                headers,
                buffer=BytesIO(data['body'].encode()),
            )
        except KeyError:
            return None

        return response

    def _load_cache_response(self, request):
        if request.method == 'GET':
            key = self._generate_cache_key(request)
            if self.cache.exists(key):
                value = self.cache.get(key)
                return self._deserialize_from_cache(value)
        return None

    def _save_cache_response(self, response):
        if response.request.method == 'GET' and response.code == 200:
            key = self._generate_cache_key(response.request)
            if not self.cache.exists(key):
                value = self._serialize_to_cache(response)
                self.cache.set(key, value, self.cache_key_ttl)
        return None

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

        self.cache_meta_data.process_request(request)

        response = self._load_cache_response(request)

        if not response:
            response = yield self._http_client.fetch(
                request,
                raise_error=False,
            )
            self._save_cache_response(response)

        data = self._format_output(response)
        return data  # noqa
