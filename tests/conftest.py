import gc
import os

# must happen before PyQt5 is imported anywhere: without a platform plugin Qt
# aborts on a machine with no display
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from PyQt5.QtWidgets import QApplication  # noqa: E402

from amaranth_companion.module import Module  # noqa: E402
from amaranth_companion.blocks import PortSpec  # noqa: E402
from amaranth_companion.module.element import Edge, Node  # noqa: E402
from amaranth_companion.module.element.graphics_item import (  # noqa: E402
    NodeContentWidget,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pytest_configure(config):
    """Measure the worker subprocesses as well as this process.

    Introspection, simulation, formal checking and waveform runs all happen in
    a ``python -m`` subprocess, which is most of the point of them. Coverage
    only follows a child process when ``COVERAGE_PROCESS_START`` names a
    config file, and children inherit the environment, so setting it here is
    enough -- without it the most carefully tested code in the project reads
    as untested.
    """
    try:
        import coverage
    except ImportError:
        return

    if coverage.Coverage.current() is None:
        return  # not a coverage run

    os.environ.setdefault(
        "COVERAGE_PROCESS_START", os.path.join(PROJECT_ROOT, "pyproject.toml")
    )


def ports(*names: str) -> list[PortSpec]:
    """Port specs from suffixed names: ``ports("a_in", "o_out")``."""
    return [PortSpec.from_name(name) for name in names]


DEFAULT_PORTS = ports("a_in", "b_in", "o_out")


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

    def _make(module, title="", node_ports=None, pos=(0, 0), text=""):
        node = Node(
            module,
            ports=DEFAULT_PORTS if node_ports is None else node_ports,
            content_widget=NodeContentWidget(text=text),
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
    module.add_edge(
        Edge(nodes[0].output_sockets["o_out"], nodes[1].input_sockets["a_in"])
    )
    module.add_edge(
        Edge(nodes[1].output_sockets["o_out"], nodes[2].input_sockets["a_in"])
    )
    module.history.reset()
    return module, nodes
