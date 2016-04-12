import logging
import logging.config
from os import environ
from os.path import (
    join,
    dirname,
    abspath,
)
import config

env_config_key = environ.get('NIGHTPARTY_TORNADO', 'DEVELOPMENT')

config = config.from_yaml(
    join(dirname(abspath(__file__)), 'config.yaml'),
    env_config_key,
)

globals().update(config)
log_cfg = config.get("LOG_CFG")
if log_cfg:
    logging.config.dictConfig(log_cfg)
