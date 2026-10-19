"""Mouse and keyboard on the canvas.

The oldest code in the project and the least covered: panning, dragging an
edge out of a socket, rubber-band selection, delete. The handlers take real
``QMouseEvent``s, so the tests make real ``QMouseEvent``s rather than calling
the private helpers underneath.
"""

import pytest

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QKeyEvent, QMouseEvent
from PyQt5.QtWidgets import QGraphicsView

from amaranth_companion.blocks.library import library
from amaranth_companion.design import Design
from amaranth_companion.module.element import Edge
from amaranth_companion.module.instantiate import instantiate
from amaranth_companion.module.scene import ModuleSceneView
from amaranth_companion.module.scene.module_scene_view import DragMode

from conftest import ports


@pytest.fixture
def design(qapp):
    return Design()


@pytest.fixture
def view(design):
    """A view big enough to have a usable viewport."""
    view = ModuleSceneView(design.current_module)
    view.resize(800, 600)
    view.show()
    return view


def press(view, button, scene_pos=(0, 0)):
    point = view.mapFromScene(QPointF(*scene_pos))
    event = QMouseEvent(
        QEvent.MouseButtonPress,
        QPointF(point),
        button,
        button,
        Qt.NoModifier,
    )
    view.mousePressEvent(event)
    return event


def release(view, button, scene_pos=(0, 0)):
    point = view.mapFromScene(QPointF(*scene_pos))
    event = QMouseEvent(
        QEvent.MouseButtonRelease,
        QPointF(point),
        button,
        Qt.NoButton,
        Qt.NoModifier,
    )
    view.mouseReleaseEvent(event)
    return event


def move(view, scene_pos):
    point = view.mapFromScene(QPointF(*scene_pos))
    view.mouseMoveEvent(
        QMouseEvent(
            QEvent.MouseMove, QPointF(point), Qt.NoButton, Qt.NoButton, Qt.NoModifier
        )
    )


def double_click(view, scene_pos):
    point = view.mapFromScene(QPointF(*scene_pos))
    view.mouseDoubleClickEvent(
        QMouseEvent(
            QEvent.MouseButtonDblClick,
            QPointF(point),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
    )


def socket_scene_pos(socket):
    return (socket.scene_pos.x(), socket.scene_pos.y())


# --- panning ----------------------------------------------------------------


def test_the_middle_button_pans(view):
    """QGraphicsView only pans with the left button, so it is translated."""
    press(view, Qt.MiddleButton)

    assert view.dragMode() == QGraphicsView.ScrollHandDrag


def test_releasing_the_middle_button_stops_panning(view):
    press(view, Qt.MiddleButton)
    release(view, Qt.MiddleButton)

    assert view.dragMode() == QGraphicsView.NoDrag


def test_the_right_button_is_left_alone(view):
    """Anything that is not a pan or a drag goes to the base implementation."""
    press(view, Qt.RightButton)
    release(view, Qt.RightButton)

    assert view.dragMode() == QGraphicsView.NoDrag


# --- selection --------------------------------------------------------------


def test_pressing_empty_canvas_starts_a_rubber_band(view):
    press(view, Qt.LeftButton, (-2000, -2000))

    assert view.dragMode() == QGraphicsView.RubberBandDrag


def test_pressing_a_node_does_not_rubber_band(view, design):
    node = design.instantiate(library().require("builtin.code"))
    node.pos = (0, 0)

    press(view, Qt.LeftButton, (60, 60))

    assert view.dragMode() == QGraphicsView.NoDrag


# --- dragging an edge -------------------------------------------------------


@pytest.fixture
def two_blocks(design, view):
    module = design.current_module
    source = instantiate(
        module, library().require("builtin.port_in"), text="a", pos=(-400, 0)
    )
    sink = instantiate(
        module, library().require("builtin.port_out"), text="b", pos=(300, 0)
    )
    return module, source, sink


def test_pressing_a_socket_starts_an_edge(view, two_blocks):
    _module, source, _sink = two_blocks

    press(view, Qt.LeftButton, socket_scene_pos(source.output_sockets["a_in"]))

    assert view._drag.mode is DragMode.EDGE
    assert view._drag.start_socket is source.output_sockets["a_in"]


def test_the_preview_follows_the_cursor(view, two_blocks):
    _module, source, _sink = two_blocks
    press(view, Qt.LeftButton, socket_scene_pos(source.output_sockets["a_in"]))

    move(view, (120, 80))

    assert view._drag.edge_item.end_point is not None


def test_dropping_on_a_socket_connects_it(view, two_blocks):
    module, source, sink = two_blocks

    press(view, Qt.LeftButton, socket_scene_pos(source.output_sockets["a_in"]))
    release(view, Qt.LeftButton, socket_scene_pos(sink.input_sockets["b_out"]))

    assert len(list(module.edges)) == 1
    assert view._drag.mode is DragMode.NONE


def test_dropping_on_empty_canvas_connects_nothing(view, two_blocks):
    module, source, _sink = two_blocks

    press(view, Qt.LeftButton, socket_scene_pos(source.output_sockets["a_in"]))
    release(view, Qt.LeftButton, (-3000, -3000))

    assert list(module.edges) == []
    assert view._drag.mode is DragMode.NONE


def test_an_input_keeps_only_its_newest_edge(view, design):
    """An input takes one edge; a second drop replaces the first."""
    module = design.current_module
    first = instantiate(
        module, library().require("builtin.port_in"), text="a", pos=(-400, -200)
    )
    second = instantiate(
        module, library().require("builtin.port_in"), text="c", pos=(-400, 200)
    )
    sink = instantiate(
        module, library().require("builtin.port_out"), text="b", pos=(300, 0)
    )

    for origin, name in ((first, "a_in"), (second, "c_in")):
        press(view, Qt.LeftButton, socket_scene_pos(origin.output_sockets[name]))
        release(view, Qt.LeftButton, socket_scene_pos(sink.input_sockets["b_out"]))

    assert len(list(module.edges)) == 1
    assert len(sink.input_sockets["b_out"].edges) == 1


# --- deleting ---------------------------------------------------------------


def test_delete_removes_the_selection(view, design, make_node):
    module = design.current_module
    node = make_node(module, node_ports=ports("a_in", "o_out"))
    node.graphics_item.setSelected(True)

    view.delete_selected()

    assert module.nodes == {}


def test_delete_takes_the_edges_with_it(view, two_blocks):
    module, source, sink = two_blocks
    module.add_edge(Edge(source.output_sockets["a_in"], sink.input_sockets["b_out"]))
    source.graphics_item.setSelected(True)

    view.delete_selected()

    assert list(module.edges) == []
    assert len(module.nodes) == 1


def test_the_delete_key_deletes(view, design, make_node):
    module = design.current_module
    make_node(module).graphics_item.setSelected(True)

    view.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))

    assert module.nodes == {}


def test_delete_does_nothing_while_editing_a_block(view, design, make_node):
    """Otherwise backspacing in a code block would delete the block."""
    module = design.current_module
    make_node(module).graphics_item.setSelected(True)
    view.node_edit = True

    view.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))

    assert len(module.nodes) == 1


def test_leaving_an_edit_records_one_undo_step(view, design, make_node):
    module = design.current_module
    make_node(module)
    design.history.check_in()
    before = design.history.is_undoable

    view.node_edit = True
    view.node_edit = False

    assert design.history.is_undoable == before


# --- zooming ----------------------------------------------------------------


def test_zooming_in_scales_up(view):
    before = view.transform().m11()

    view.zoom_in_out(1)

    assert view.transform().m11() > before


def test_zooming_is_clamped(view):
    for _ in range(50):
        view.zoom_in_out(1)
    most = view.transform().m11()

    view.zoom_in_out(1)

    assert view.transform().m11() == most


def test_zooming_out_is_clamped_too(view):
    for _ in range(50):
        view.zoom_in_out(-1)
    least = view.transform().m11()

    view.zoom_in_out(-1)

    assert view.transform().m11() == least


def test_fitting_an_empty_scene_resets_the_zoom(view):
    view.zoom_in_out(3)

    view.fit_contents()

    assert view.transform().m11() == pytest.approx(1.0)


def test_fitting_centres_on_the_contents(view, design):
    """Wherever the design sits, fitting brings it into view."""
    node = design.instantiate(library().require("logic.and2"))
    node.pos = (4000, 3000)

    view.fit_contents()

    centre = view.mapToScene(view.viewport().rect().center())
    bounds = design.current_module.scene.itemsBoundingRect()
    assert bounds.center().x() == pytest.approx(centre.x(), abs=20)
    assert bounds.center().y() == pytest.approx(centre.y(), abs=20)


def test_fitting_zooms_in_on_a_small_design(view, design):
    """A single block in a big viewport should fill it, not sit in a corner."""
    design.instantiate(library().require("logic.and2")).pos = (0, 0)

    view.fit_contents()

    assert view.transform().m11() > 1.0


def test_fitting_zooms_out_for_a_wide_design(view, design):
    first = design.instantiate(library().require("logic.and2"))
    second = design.instantiate(library().require("logic.not"))
    first.pos, second.pos = (-3000, 0), (3000, 0)

    view.fit_contents()

    assert view.transform().m11() < 1.0


# --- descending -------------------------------------------------------------


def test_double_clicking_a_hierarchical_block_emits(view, design):
    node = design.instantiate(library().require("logic.and2"))
    node.pos = (0, 0)
    seen = []
    view.node_activated.connect(seen.append)

    double_click(view, (60, 60))

    assert seen == [node]


def test_double_clicking_a_plain_block_does_not(view, design):
    node = instantiate(
        design.current_module, library().require("builtin.code"), pos=(0, 0)
    )
    seen = []
    view.node_activated.connect(seen.append)

    double_click(view, (60, 60))

    assert seen == []


def test_double_clicking_empty_canvas_does_not(view, design):
    seen = []
    view.node_activated.connect(seen.append)

    double_click(view, (-3000, -3000))

    assert seen == []


# --- the view's module ------------------------------------------------------


def test_setting_a_module_shows_its_scene(view, design):
    other = Design()

    view.module = other.current_module

    assert view.scene() is other.current_module.scene
    assert view.module is other.current_module


def test_the_view_reaches_the_history(view, design):
    assert view.history is design.history


def test_entering_and_leaving_switch_the_zoom_anchor(view):
    view.enterEvent(QEvent(QEvent.Enter))
    assert view.transformationAnchor() == QGraphicsView.AnchorUnderMouse

    view.leaveEvent(QEvent(QEvent.Leave))
    assert view.transformationAnchor() == QGraphicsView.AnchorViewCenter
