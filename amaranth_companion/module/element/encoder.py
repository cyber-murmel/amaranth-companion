from json import JSONEncoder

from .node import Node
from .edge import Edge
from .element import ModuleElement


class ModuleElementEncoder(JSONEncoder):
    def default(self, obj: ModuleElement):
        if isinstance(obj, Node):
            return {
                # "uuid": obj.uuid,
                "pos": obj.pos,
                "text": obj.content_widget.text_edit.toPlainText(),
            }
        if isinstance(obj, Edge):
            module = obj.module
            start_socket = obj.start_socket
            end_socket = obj.end_socket
            # start_node_id = start_socket.node.id
            # end_node_id = end_socket.node.id
            return {
                "start": {
                    "node_uuid": start_socket.node.uuid,
                    "socket_name": start_socket.name,
                },
                "end": {
                    "node_uuid": end_socket.node.uuid,
                    "socket_name": end_socket.name,
                },
            }

        return JSONEncoder.default(self, obj)
