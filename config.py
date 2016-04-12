from copy import deepcopy
from functools import reduce
import yaml


def from_yaml(path, config_key):
    with open(path) as file:
        config = yaml.load(file)
        path = [config_key, ]
        v = config[config_key]
        while '_parent' in v:
            p = v['_parent']
            if p in path:
                raise StandardError("Inheritance loop! {}->!!{}!!".format('->'.join(path), p))
            if p not in config:
                raise StandardError('Wrong parrent {}'.format(p))

            path.append(p)
            v = config[p]

        path.reverse()
        res = reduce(merge_dict, map(config.get, path))
        if '_parent' in res:
            del(res['_parent'])

    return res


def merge_dict(a, b):
    result = deepcopy(a)
    for k, v in b.items():
        if k in result and isinstance(result[k], dict):
            result[k] = merge_dict(result[k], v)
        else:
            result[k] = deepcopy(v)
    return result

if __name__ == '__main__':
    from os.path import dirname, abspath, join
    from pprint import pprint as pp
    pp(
        from_yaml(join(dirname(abspath(__file__)), 'config.yaml'))
    )
