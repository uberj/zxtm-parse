import simplejson as json
from jsonpointer import resolve_pointer
import sys
#import pprint as pp


class PointerPath(object):
    rmap = {
        '/': '~1',
        ' ': '/ ',
        '~': '~0',
    }

    def __init__(self, path):
        new_path = []
        for c in path:
            new_path.append(self.rmap.get(c, c))
        self.path = ''.join(new_path)

    def __str__(self):
        return self.path

    def __add__(self, y):
        return self.path + y

    def __radd__(self, y):
        return y + self.path

    def __repr__(self):
        return "<PointerPath: {0}>".format(self.path)


class Pool(object):
    def __init__(self, name, blob):
        self.name = name
        self.blob = blob

    def __str__(self):
        return self.blob.show_paths(prefix="{0}.".format(self.name))

    def __repr__(self):
        return str(self)

    @property
    def status(self):
        return self.blob.get_path('/status')

    @property
    def note(self):
        return self.blob.get_path('/note')

    @property
    def nodes_table(self):
        return self.blob.get_path('/info/properties/basic').json['nodes_table']


class TIG(object):
    def __init__(self, name, blob):
        self.name = name
        self.blob = blob

    def __str__(self):
        return self.blob.show_paths(prefix="{0}.".format(self.name))

    def __repr__(self):
        return str(self)

    @property
    def status(self):
        return self.blob.get_path('status')

    @property
    def note(self):
        return self.blob.get_path('note')

    @property
    def ipaddresses(self):
        return self.blob.get_path('info/properties/basic').json['ipaddresses']


class ZLB(object):
    def __init__(self, blob):
        self.blob = blob
        self._tigs = None
        self._pools = None

    def __str__(self):
        return str(self.blob)

    def __repr__(self):
        return str(self)

    @property
    def tigs(self):
        if not self._tigs:
            self._tigs = []
            for tig_name in self.blob.get_path('/tigs').json:
                self._tigs.append(
                    TIG(tig_name, self.blob.get_path('tigs/' + tig_name))
                )
        return self._tigs

    @property
    def pools(self):
        if not self._pools:
            self._pools = []
            for pool_name in self.blob.get_path('/pools').json:
                self._pools.append(Pool(
                    pool_name, self.blob.get_path('/pools/' + pool_name)
                ))
        return self._pools


class Blob(object):
    def __init__(self, json_blob):
        self.json_blob = json_blob

    def __str__(self):
        return self.show_paths()

    def __repr__(self):
        return str(self)

    @property
    def json(self):
        return self.json_blob

    def get_path(self, path):
        try:
            return Blob(resolve_pointer(self.json_blob, path))
        except KeyError:
            raise KeyError("[ERROR] couldn't parse {0}".format(path))

    def show_paths(self, prefix=''):
        return '\n'.join(self.list_paths(prefix))

    def list_paths(self, prefix):
        return self._list_path(prefix, self.json_blob)

    def list_path(self, path, prefix=''):
        blob = self.get_path(path)
        return self._list_path(prefix, blob.json)

    def _list_path(self, prefix, json_blob):
        if isinstance(json_blob, list):
            return json_blob

        result = []
        more = []
        for key, value in json_blob.iteritems():
            if isinstance(value, dict):
                more += self._list_path(prefix + key + '.', value)
            elif isinstance(value, list):
                for cn in value:
                    more += self._list_path(prefix, {key: cn})
            else:
                result.append("{0}{1} = {2}".format(prefix, key, value))
        return result + more


class ZXTMState(object):
    def __init__(self, ulr=None, filename=None):
        with open(filename, 'r') as fd:
            self.blob = Blob(json.load(fd))

    @property
    def zxtms(self):
        for zxtm in iter(zxtm for zxtm in self.blob.json['zxtms']):
            ppath = '/zxtms/' + PointerPath(zxtm)
            yield ZLB(self.blob.get_path(ppath))

if __name__ == '__main__':
    zs = ZXTMState(filename='zxtm.json')
    for zxtm in zs.zxtms:
        for pool in zxtm.pools:
            print '-' * 50
            print 'Name: ' + pool.name
            print pool
        sys.exit(0)
