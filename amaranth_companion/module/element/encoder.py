from json import JSONEncoder

from .node import Node
from .edge import Edge
from .element import ModuleElement


class ModuleElementEncoder(JSONEncoder):
    def default(self, obj: ModuleElement):
        if isinstance(obj, Node):
            return {"pos": obj.pos}
        if isinstance(obj, Edge):
            module = obj.module
            start_socket = obj.start_socket
            end_socket = obj.end_socket
            start_node_index = module._nodes.index(start_socket.node)
            end_node_index = module._nodes.index(end_socket.node)
            return {
                "start": {
                    "node_index": start_node_index,
                    "socket_name": start_socket.name,
                },
                "end": {"node_index": end_node_index, "socket_name": end_socket.name},
            }

        return JSONEncoder.default(self, obj)
