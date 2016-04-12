from .exceptions import (  # noqa
    DBApiError,
)
from .direct_api import DBApiDirect  # noqa
from .cached_api import DBApiCached  # noqa


def get_db_api(is_cached=True):
    if is_cached:
        return DBApiCached
    return DBApiDirect
