import socket
from time import time
import logging

from tornado import gen
from tornado.platform.caresresolver import CaresResolver


class Resolver(CaresResolver):
    def initialize(self, *args, **kwargs):
        self._dns_record_ttl = kwargs.pop('ttl', 3600)
        self._dns_cache = {}
        super().initialize(*args, **kwargs)

    @gen.coroutine
    def resolve(self, host, port, family=socket.AF_INET):
        now = time()
        self._dns_cache = {k: v for k, v in self._dns_cache.items() if v['ttl'] > now}
        if ((host, port) not in self._dns_cache):
            addresses = yield super().resolve(host, port, family=family)
            self._dns_cache[(host, port)] = dict(
                addresses=addresses,
                ttl=now + self._dns_record_ttl,
            )
            logging.debug("Resolved hostname {}: {}".format(host, addresses))
        else:
            addresses = self._dns_cache[(host, port)]['addresses']

        return addresses  # noqa
