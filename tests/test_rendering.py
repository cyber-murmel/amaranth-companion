"""Painting the canvas.

Every graphics item's ``paint`` and the scene's ``drawBackground`` only run
when something actually renders, which no other test does -- so a crash in
them, or a theme colour that resolves to nothing, would go unnoticed until the
window opened. Rendering offscreen into a QImage exercises the lot.
"""

import pytest

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QImage, QPainter

from amaranth_companion.blocks.library import library
from amaranth_companion.design import Design
from amaranth_companion.examples import find, open_example
from amaranth_companion.module.element import Edge
from amaranth_companion.module.instantiate import instantiate
from amaranth_companion.theme import ThemeMode, theme_manager

WIDTH, HEIGHT = 640, 480


@pytest.fixture
def design(qapp):
    return Design()


@pytest.fixture(params=[ThemeMode.LIGHT, ThemeMode.DARK], ids=["light", "dark"])
def themed(qapp, request):
    """Each rendering check runs under both themes."""
    manager = theme_manager()
    previous = manager.mode
    manager.apply(request.param, persist=False)
    yield request.param
    manager.apply(previous, persist=False)


def render(scene, width=WIDTH, height=HEIGHT) -> QImage:
    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(0)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    try:
        scene.render(
            painter,
            QRectF(0, 0, width, height),
            QRectF(-width / 2, -height / 2, width, height),
        )
    finally:
        painter.end()

    return image


def colours(image: QImage) -> set[int]:
    return {
        image.pixel(x, y)
        for x in range(0, image.width(), 4)
        for y in range(0, image.height(), 4)
    }


# --- the canvas -------------------------------------------------------------


def test_an_empty_scene_draws_its_grid(design, themed):
    """``drawBackground`` is the only thing on an empty canvas."""
    image = render(design.root.scene)

    # the canvas colour and at least one grid line
    assert len(colours(image)) >= 2


def test_the_grid_follows_the_theme(design):
    manager = theme_manager()
    previous = manager.mode
    try:
        manager.apply(ThemeMode.LIGHT, persist=False)
        light = render(design.root.scene)
        manager.apply(ThemeMode.DARK, persist=False)
        dark = render(design.root.scene)
    finally:
        manager.apply(previous, persist=False)

    assert light != dark


# --- block kinds ------------------------------------------------------------


@pytest.mark.parametrize(
    "block_id",
    [
        "logic.and2",
        "logic.not",
        "builtin.code",
        "builtin.port_in",
        "builtin.port_param",
        "builtin.variable",
    ],
)
def test_every_block_kind_paints(design, themed, block_id):
    node = design.instantiate(library().require(block_id))
    node.pos = (-200, -150)

    assert len(colours(render(design.root.scene))) > 1


def test_a_hierarchical_block_paints_its_icon(design, themed):
    design.instantiate(library().require("logic.and2")).pos = (-200, -150)

    # the symbol is a proxied widget, so it only reaches the image if the
    # whole node -- bands, outline, proxy -- painted
    assert len(colours(render(design.root.scene))) > 3


def test_a_selected_block_paints_differently(design, themed):
    node = design.instantiate(library().require("logic.and2"))
    node.pos = (-200, -150)

    unselected = render(design.root.scene)
    node.graphics_item.setSelected(True)
    selected = render(design.root.scene)

    assert unselected != selected


# --- sockets and edges ------------------------------------------------------


def test_signal_and_parameter_sockets_both_paint(design, themed):
    """One is a circle and the other a square; both go through ``paint``."""
    node = design.instantiate(library().require("logic.and2"))
    node.pos = (-200, -150)

    kinds = {socket.kind for socket in node.sockets}
    assert len(kinds) == 2
    assert len(colours(render(design.root.scene))) > 1


def test_an_edge_paints(design, themed):
    module = design.current_module
    source = instantiate(
        module, library().require("builtin.port_in"), text="a", pos=(-300, -100)
    )
    sink = instantiate(
        module, library().require("builtin.port_out"), text="b", pos=(100, -100)
    )
    assert module.add_edge(
        Edge(source.output_sockets["a_in"], sink.input_sockets["b_out"])
    )

    with_edge = render(module.scene)
    module.remove_edge(next(iter(module.edges)))

    assert with_edge != render(module.scene)


def test_a_selected_edge_paints_differently(design, themed):
    module = design.current_module
    source = instantiate(
        module, library().require("builtin.port_in"), text="a", pos=(-300, -100)
    )
    sink = instantiate(
        module, library().require("builtin.port_out"), text="b", pos=(100, -100)
    )
    module.add_edge(Edge(source.output_sockets["a_in"], sink.input_sockets["b_out"]))
    edge = next(iter(module.edges))

    plain = render(module.scene)
    edge.graphics_item.setSelected(True)

    assert plain != render(module.scene)


def test_a_detached_edge_paints(design, themed):
    """The preview that follows the cursor has no edge behind it."""
    from PyQt5.QtCore import QPointF

    from amaranth_companion.module.element.graphics_item import EdgeGraphicsItem

    item = EdgeGraphicsItem(None)
    item.set_points(QPointF(-200, -100), QPointF(200, 100))
    design.root.scene.addItem(item)

    assert len(colours(render(design.root.scene))) > 1


# --- a whole design ---------------------------------------------------------


@pytest.mark.parametrize("name", ["blinker", "nand", "logic-gates"])
def test_a_shipped_example_renders(qapp, name):
    """The examples are what a new user sees first."""
    design = open_example(find(name))

    assert len(colours(render(design.root.scene, 1000, 700))) > 3


def test_descending_renders_the_implementation(qapp):
    design = open_example(find("logic-gates"))
    gate = next(iter(design.root.nodes.values()))
    design.enter(gate)

    assert len(colours(render(design.current_module.scene))) > 1


def test_a_block_with_an_error_still_paints(design, themed):
    """A broken block must draw, or the user cannot see what to fix."""
    node = instantiate(
        design.current_module,
        library().require("builtin.code"),
        text="class Broken(:\n",
        pos=(-200, -150),
    )

    assert node.error
    assert len(colours(render(design.root.scene))) > 1
