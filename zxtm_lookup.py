import simplejson as json
import sys
from jsonpointer import resolve_pointer


def log(msg, level='error'):
    if level == 'error':
        sys.stderr.write(str(msg) + '\n')


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
        self.tig = None
        self.vservers = []

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
        if not self.blob:
            return []
        return self.blob.get_path('/info/properties/basic').json['nodes_table']


class TIG(object):
    def __init__(self, name, blob):
        self.name = name
        self.blob = blob
        self.vservers = []

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
    def ipaddresses(self):
        return self.blob.get_path('/info/properties/basic').json['ipaddresses']


class Nodes(object):
    """
    This is meant to be an inverted index of the ZuesState object that maps
    hosts to tigs, pools, and virtual servers.
    """
    def __init__(self, zstate):
        self._nodes = {}
        for pool in zstate.pools.values():
            for node in pool.nodes_table:
                node['node_id'] = node['node'].split(':')[0]
                self._process_nodes(node, pool)

    def _process_nodes(self, node_instance, pool):
        node = self._nodes.setdefault(node_instance['node_id'], Node())
        node.instances.append((node_instance, pool))

    def __iter__(self):
        def nodes():
            for node_name, node in self._nodes.iteritems():
                yield (node_name, node)
        return nodes()

    def __getitem__(self, node_id):
        return self._nodes[node_id]


class Node(object):
    """
    Node is a representation of an IP or hostname. 10.1.1.1:500 10.1.1.1:501
    would be the *same* node.
    """
    def __init__(
        self, node_id=None
    ):
        self.node_id = node_id
        self.instances = []

    def __str__(self):
        return "node:{0} pool:{1}".format(
            self.node_id, ', '.join(pool.name for pool in self.pools)
        )

    def __repr__(self):
        return "<Node:{0}>".format(self)


class ZXTM(object):
    def __init__(self, blob):
        self.blob = blob
        self._tigs = None
        self._pools = None
        self._vservers = None
        self._nodes = None
        self.zip_tigs_and_pools()

    def __str__(self):
        return str(self.blob)

    def __repr__(self):
        return str(self)

    @property
    def url(self):
        return self.blob.json['url']

    @property
    def nodes(self):
        if not self._nodes:
            self._nodes = Nodes(self)
        return self._nodes

    @property
    def tigs(self):
        if not self._tigs:
            self._tigs = {}
            for tig_name in self.blob.get_path('/tigs').json:
                if tig_name in self._tigs:
                    log(
                        "[WARNING] already seen tig with name {0}"
                        .format(tig_name)
                    )
                self._tigs[tig_name] = TIG(
                    tig_name,
                    self.blob.get_path('/tigs/' + tig_name)
                )
        return self._tigs

    @property
    def pools(self):
        if not self._pools:
            self._pools = {
                'discard': Pool(
                    'discard', None
                )
            }
            for pool_name in self.blob.get_path('/pools').json:
                if pool_name in self._pools:
                    print (
                        "[WARNING] already seen pool with name {0}"
                        .format(pool_name)
                    )
                self._pools[pool_name] = Pool(
                    pool_name, self.blob.get_path('/pools/' + pool_name)
                )
        return self._pools

    @property
    def vservers(self):
        if not self._vservers:
            self._vservers = {}
            for vserver_name in self.blob.get_path('/servers').json:
                if vserver_name in self._vservers:
                    log(
                        "[WARNING] already seen vserver with name {0}"
                        .format(vserver_name)
                    )
                self._vservers[vserver_name] = VServer(
                    vserver_name,
                    self.blob.get_path('/servers/' + vserver_name)
                )
        return self._vservers

    def zip_tigs_and_pools(self):
        for vserver_name, vserver in self.vservers.iteritems():
            if vserver.pool_name not in self.pools:
                log("Parsing zxtm {0}".format(self.url))
                log("Couldn't find a pool for {0}".format(repr(vserver)))
            else:
                vserver.pool = self.pools[vserver.pool_name]
                self.pools[vserver.pool_name].vservers.append(vserver)

            for vserver.tig_name in vserver.listening_tigs:
                if not vserver.tig_name in self.tigs:
                    log("Parsing zxtm {0}".format(self.url))
                    log("Couldn't find a tig for {0}".format(repr(vserver)))
                else:
                    vserver.tigs.append(self.tigs[vserver.tig_name])
                    self.tigs[vserver.tig_name].vservers.append(vserver)


class VServer(object):
    def __init__(self, name, blob):
        self.name = name
        self.blob = blob
        self.tigs = []

    def __str__(self):
        return self.blob.show_paths(prefix="{0}.".format(self.name))

    def __repr__(self):
        return "<VServer: name={0} pool={1} tigs={2}>".format(
            self.name, self.pool_name, ','.join(tig.name for tig in self.tigs)
        )

    @property
    def pool_name(self):
        return self.blob.get_path('/info/properties/basic').json[
            'pool'
        ]

    @property
    def listening_tigs(self):
        return self.blob.get_path('/info/properties/basic').json[
            'listen_on_traffic_ips'
        ]


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
    def __init__(self, ulr=None, filename=None, version='0.005'):
        with open(filename, 'r') as fd:
            self.blob = Blob(json.load(fd))

        if self.version != version:
            log("Version mismatch!")

    @property
    def version(self):
        return self.blob.json['version']

    @property
    def zxtms(self):
        for zxtm in iter(zxtm for zxtm in self.blob.json['zxtms']):
            ppath = '/zxtms/' + PointerPath(zxtm)
            yield ZXTM(self.blob.get_path(ppath))


class AllNodes(ZXTMState):
    def __init__(self, zs):
        self.zs = zs

    def find(self, node_id):
        for zxtm in self.zs.zxtms:
            try:
                return zxtm.nodes[node_id]
            except KeyError:
                continue
        raise KeyError("No node {0}".format(node_id))


if __name__ == '__main__':
    zs = ZXTMState(filename='zxtm.json')
    allnodes = AllNodes(zs)
    if len(sys.argv) != 2:
        print "usage: zxtm_lookup <host_id>"
        sys.exit(1)
    host_id = sys.argv[1]
    node = allnodes.find(host_id)
    log("Looking up info for {0}\n".format(host_id))
    for node, pool in node.instances:
        for vserver in pool.vservers:
            for tig in vserver.tigs:
                log(
                    "Node {node} is backing TIG {tig} in the pool {pool}. "
                    "Configuration is on the {vserver} vserver".format(
                        node=node['node'], tig=tig.name, pool=pool.name,
                        vserver=vserver.name
                    )
                )
