import logging
from functools import partial

import redis

from tornado import gen


class RedisState:
    def __init__(self, app):
        self.app = app
        self.redis = self.app.redis_connection
        self.options = self.app.options

    def get(self, key):
        return None

    def set(self, key, value, key_ttl):
        pass

    def delete(self, key):
        pass

    def exists(self, key):
        return False


class RedisStateDisconnected(RedisState):

    def __str__(self):
        return "RedisState(DISCONNECTED)"


class RedisStateConnected(RedisState):

    def get(self, key):
        if self.exists(key):
            return self.redis.get(key)
        return None

    def set(self, key, value, key_ttl=None):
        self.redis.set(key, value)
        self.redis.expire(key, key_ttl or self.options.get('key_ttl'))

    def delete(self, key):
        self.redis.delete(key)

    def exists(self, key):
        return bool(self.redis.exists(key))

    def __str__(self):
        return "RedisState(CONNECTED)"


class RedisCache:
    (CONNECTED, DISCONNECTED) = ('connected', 'disconnected')

    def __init__(self, *args, **kwargs):
        self.redis_connection = redis.Redis(*args, **kwargs)
        self.options = {}

        self.is_running = True

        self.state_map = {
            self.CONNECTED: RedisStateConnected(self),
            self.DISCONNECTED: RedisStateDisconnected(self),
        }

        self.state = self.state_map[self.DISCONNECTED]

    def initialize(self, key_ttl=None):
        if key_ttl:
            self.options['key_ttl'] = key_ttl

    def send(self, func_name, *args, **kwargs):
        res = None
        try:
            res = getattr(self.state, func_name)(*args, **kwargs)
        except redis.ConnectionError:
            self.state = self.state_map[self.DISCONNECTED]

        return res

    def __getattr__(self, name):
        if name in ['get', 'set', 'delete', 'exists']:
            return partial(self.send, name)
        raise AttributeError(name)

    def stop(self):
        self.is_running = False

    @gen.coroutine
    def run(self):
        logging.info('redis client start')
        reconnect_attempt = 0
        while self.is_running:
            if self.state == self.state_map[self.DISCONNECTED]:
                try:
                    reconnect_attempt += 1
                    if self.redis_connection.ping():
                        logging.info('redis connected')
                        self.state = self.state_map[self.CONNECTED]
                        reconnect_attempt = 0
                except redis.ConnectionError:
                    logging.info('can"t connect')
                finally:
                    sleep_interval = 2 ** reconnect_attempt
                    if sleep_interval > 17:
                        sleep_interval = 17
            else:
                sleep_interval = 4

            # logging.debug('%s sleep(%d)', self.state, sleep_interval)
            yield gen.sleep(sleep_interval)

        logging.info('redis client stopped')
