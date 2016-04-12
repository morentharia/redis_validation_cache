from pprint import pprint as pp  # noqa
from collections import OrderedDict
from urllib.parse import urlencode, urlparse, parse_qsl
import json

from tornado.escape import utf8


class JinjaTemplateMixin:
    """
    Миксин который заменяет tornado Template Engine на Jinja2
    Важно: предполагается что сам инстанс jinja проинициалиирован
    в self.application.jinja
    """
    def initialize(self, *args, **kwargs):
        self.__jinja = self.application.jinja
        super().initialize(*args, **kwargs)

    def render(self, template, **kwargs):
        context = kwargs
        context.update(self.get_template_namespace())
        self.xsrf_token
        rendered_text = self.__jinja.get_template(template).render(context)
        self.write(rendered_text)
        self.flush()

    def render_json(self, data):
        self.xsrf_token
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(data))


class CacheMixin:
    """
    Кэширует GET запрос
    """

    def initialize(self, *args, **kwargs):
        self.__cache = self.application.cache
        self.__write_buffer = []
        super().initialize(*args, **kwargs)

    def prepare(self):
        if self.request.method == 'GET':
            self.key = self.__generate_key()
            if self.__cache.exists(self.key):
                cached_value = self.__cache.get(self.key)
                super().write(cached_value)
                super().finish()
                return

        super().prepare()

    def __generate_key(self):
        res = urlparse('http://' + self.request.uri + self.request.query)
        q = parse_qsl(res.query)
        q.sort()
        query = urlencode(OrderedDict(q))

        key = '||'.join([
            # request.method,
            res.path,
            query,
        ])
        return key

    def write(self, chunk):
        chunk = utf8(chunk)
        self.__write_buffer.append(chunk)
        super().write(chunk)

    def finish(self):
        chunk = b"".join(self.__write_buffer)
        key = self.__generate_key()
        self.__cache.set(
            key, chunk,
            key_ttl=self.__cache.options.get('key_ttl', 5)
        )
        super().finish()
