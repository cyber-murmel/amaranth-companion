from .graphics_item import SocketGraphicsItem


class Socket:
    def __init__(self, socket_type, parent=None):
        self._type = socket_type

        self._graphics_item = SocketGraphicsItem(parent)

    @property
    def graphics_item(self):
        return self._graphics_item
