import gc
import os

# must happen before PyQt5 is imported anywhere: without a platform plugin Qt
# aborts on a machine with no display
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from PyQt5.QtWidgets import QApplication  # noqa: E402

from amaranth_companion.module import Module  # noqa: E402
from amaranth_companion.module.element import Edge, Node, SocketType  # noqa: E402
from amaranth_companion.module.element.graphics_item import (  # noqa: E402
    NodeContentWidget,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

DEFAULT_INPUTS = {"a": SocketType.BIT, "b": SocketType.BIT}
DEFAULT_OUTPUTS = {"o": SocketType.BIT}


#: keeps the QApplication alive for the whole process. Qt objects destroyed
#: after it dies take the interpreter down with them.
_APP = []


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole run; Qt does not allow a second one."""
    app = QApplication.instance() or QApplication([])
    _APP.append(app)
    return app


@pytest.fixture(autouse=True)
def collect_qt_garbage(qapp):
    """Destroy orphaned Qt objects while the QApplication is still alive.

    Removing a node or edge leaves its graphics item unreferenced. Letting
    those be collected at interpreter shutdown -- after Qt has torn itself
    down -- segfaults the test run even though every test passed.
    """
    yield
    gc.collect()
    qapp.processEvents()


@pytest.fixture
def make_node(qapp):
    """Build a node and add it to a module."""

    def _make(module, title="", inputs=None, outputs=None, pos=(0, 0), text=""):
        node = Node(
            module,
            NodeContentWidget(text=text),
            DEFAULT_INPUTS if inputs is None else inputs,
            DEFAULT_OUTPUTS if outputs is None else outputs,
            title=title,
        )
        module.add_node(node)
        node.pos = pos
        return node

    return _make


@pytest.fixture
def module(qapp):
    return Module()


@pytest.fixture
def chain(module, make_node):
    """Three nodes wired a -> b -> c, returned as ``(module, [a, b, c])``."""
    nodes = [
        make_node(module, title=f"n{index}", pos=(index * 300, index * 100))
        for index in range(3)
    ]
    module.add_edge(Edge(nodes[0].output_sockets["o"], nodes[1].input_sockets["a"]))
    module.add_edge(Edge(nodes[1].output_sockets["o"], nodes[2].input_sockets["a"]))
    module.history.reset()
    return module, nodes
