"""Resizing a block, renaming it, and scrolling inside it."""

import pytest

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QWheelEvent

from amaranth_companion.blocks.library import library
from amaranth_companion.design import Design
from amaranth_companion.module.element.graphics_item import NodeTitleItem
from amaranth_companion.module.element.graphics_item.node_graphics_item import (
    MIN_HEIGHT,
    MIN_WIDTH,
    SIZE_BY_KIND,
)
from amaranth_companion.module.instantiate import instantiate
from amaranth_companion.module.scene import ModuleSceneView


@pytest.fixture
def design(qapp):
    return Design()


@pytest.fixture
def view(design):
    view = ModuleSceneView(design.current_module)
    view.resize(900, 700)
    view.show()
    return view


@pytest.fixture
def code(design, view):
    """A code block on a shown view.

    The view matters: renaming commits on focus-out, and an item in a scene
    nobody is looking at never gets focus to lose.
    """
    return instantiate(
        design.current_module, library().require("builtin.code"), pos=(0, 0)
    )


def wheel(view, scene_pos, modifiers=Qt.NoModifier):
    point = view.mapFromScene(QPointF(*scene_pos))
    return QWheelEvent(
        QPointF(point),
        view.mapToGlobal(point),
        QPoint(0, -120),
        QPoint(0, -120),
        Qt.NoButton,
        modifiers,
        Qt.NoScrollPhase,
        False,
    )


# --- resizing ---------------------------------------------------------------


def test_a_block_starts_at_the_size_for_its_kind(code):
    assert code.size == SIZE_BY_KIND[code.kind]


def test_a_block_can_be_resized(code):
    code.size = (600, 460)

    assert code.size == (600, 460)
    assert code.graphics_item.boundingRect().width() == 600


def test_resizing_moves_the_content_with_it(code):
    before = code.content_widget.geometry().width()

    code.size = (600, 460)

    assert code.content_widget.geometry().width() > before


def test_resizing_moves_the_output_sockets(code):
    """Outputs live on the right edge, so they follow the width."""
    code.size = (600, 460)

    assert code.output_sockets["o_out"].graphics_item.pos().x() == 600


def test_a_block_cannot_be_dragged_smaller_than_its_minimum(code):
    code.size = (10, 10)

    assert code.size == (MIN_WIDTH, MIN_HEIGHT)


def test_the_grip_is_in_the_bottom_right_corner(code):
    grip = code.graphics_item._grip_rect()

    assert grip.right() == pytest.approx(code.size[0])
    assert grip.bottom() == pytest.approx(code.size[1])


def test_a_size_is_only_stored_once_it_differs(design, code):
    assert "size" not in design.to_dict()["nodes"][code.uuid]

    code.size = (600, 460)

    assert design.to_dict()["nodes"][code.uuid]["size"] == [600, 460]


def test_a_resized_block_round_trips(design, code):
    code.size = (600, 460)

    restored = Design()
    restored.load(design.to_dict())

    assert next(iter(restored.root.nodes.values())).size == (600, 460)


def test_resizing_a_block_inside_a_hierarchy_round_trips(design):
    gate = design.instantiate(library().require("logic.and2"))
    inner = next(
        node for node in gate.child_module.nodes.values() if node.kind.value == "code"
    )
    inner.size = (520, 380)

    restored = Design()
    restored.load(design.to_dict())

    outer = next(iter(restored.root.nodes.values()))
    rebuilt = next(
        node for node in outer.child_module.nodes.values() if node.kind.value == "code"
    )
    assert rebuilt.size == (520, 380)


# --- renaming ---------------------------------------------------------------


def test_a_title_is_not_editable_until_asked(code):
    """Otherwise clicking the title would not drag the block."""
    assert not code.graphics_item.title_item.editing


def test_renaming_commits_on_focus_out(code):
    item = code.graphics_item
    item.begin_rename()
    item.title_item.setPlainText("My Counter")

    item.title_item.clearFocus()

    assert code.title == "My Counter"
    assert not item.title_item.editing


def test_escape_puts_the_old_name_back(code):
    from PyQt5.QtGui import QKeyEvent

    item = code.graphics_item
    before = code.title
    item.begin_rename()
    item.title_item.setPlainText("scribbled over")

    item.title_item.keyPressEvent(
        QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    )

    assert code.title == before
    assert item.title_item.toPlainText() == before


def test_enter_commits(code):
    from PyQt5.QtGui import QKeyEvent

    item = code.graphics_item
    item.begin_rename()
    item.title_item.setPlainText("Accepted")

    item.title_item.keyPressEvent(
        QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    )

    assert code.title == "Accepted"


def test_an_empty_name_is_refused(code):
    """A block with no name has nothing to identify it by."""
    item = code.graphics_item
    before = code.title
    item.begin_rename()
    item.title_item.setPlainText("   ")

    item.title_item.clearFocus()

    assert code.title == before


def test_whitespace_in_a_name_is_tidied(code):
    item = code.graphics_item
    item.begin_rename()
    item.title_item.setPlainText("  spaced   out  ")

    item.title_item.clearFocus()

    assert code.title == "spaced out"


def test_renaming_is_undoable(design, code):
    design.history.check_in()
    item = code.graphics_item

    item.begin_rename()
    item.title_item.setPlainText("Renamed")
    item.title_item.clearFocus()
    design.history.undo()

    assert next(iter(design.root.nodes.values())).title != "Renamed"


def test_delete_is_suppressed_while_renaming(view, code):
    code.graphics_item.begin_rename()

    assert view.node_edit

    code.graphics_item.title_item.clearFocus()
    assert not view.node_edit


def test_double_clicking_the_title_renames(view, code):
    from PyQt5.QtGui import QMouseEvent

    item = code.graphics_item.title_item
    centre = item.sceneBoundingRect().center()
    point = view.mapFromScene(centre)
    view.mouseDoubleClickEvent(
        QMouseEvent(
            QEvent.MouseButtonDblClick,
            QPointF(point),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
    )

    assert item.editing


def test_double_clicking_a_gate_title_renames_rather_than_descends(view, design):
    """A hierarchical block's name must be editable like any other."""
    from PyQt5.QtGui import QMouseEvent

    gate = design.instantiate(library().require("logic.and2"))
    gate.pos = (0, 0)
    seen = []
    view.node_activated.connect(seen.append)

    item = gate.graphics_item.title_item
    point = view.mapFromScene(item.sceneBoundingRect().center())
    view.mouseDoubleClickEvent(
        QMouseEvent(
            QEvent.MouseButtonDblClick,
            QPointF(point),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
    )

    assert item.editing
    assert seen == []


def test_the_title_item_is_what_the_view_looks_for(code):
    assert isinstance(code.graphics_item.title_item, NodeTitleItem)


# --- scrolling --------------------------------------------------------------


@pytest.fixture
def scrollable(code):
    code.size = (600, 400)
    code.content_widget.editor.setPlainText("\n".join(f"line {n}" for n in range(300)))
    assert code.content_widget.editor.verticalScrollBar().maximum() > 0
    return code


def inside(node):
    x, y = node.pos
    return (x + node.size[0] / 2, y + node.size[1] / 2)


def test_the_wheel_scrolls_a_code_block(view, scrollable):
    editor = scrollable.content_widget.editor
    before = editor.verticalScrollBar().value()

    view.wheelEvent(wheel(view, inside(scrollable)))

    assert editor.verticalScrollBar().value() != before


def test_the_wheel_does_not_zoom_over_a_code_block(view, scrollable):
    before = view.transform().m11()

    view.wheelEvent(wheel(view, inside(scrollable)))

    assert view.transform().m11() == before


def test_the_wheel_zooms_over_the_canvas(view, scrollable):
    before = view.transform().m11()

    view.wheelEvent(wheel(view, (-3000, -3000)))

    assert view.transform().m11() != before


def test_control_wheel_zooms_even_over_a_block(view, scrollable):
    """There is always a way to zoom out from over a block."""
    before = view.transform().m11()

    view.wheelEvent(wheel(view, inside(scrollable), Qt.ControlModifier))

    assert view.transform().m11() != before


def test_a_block_with_nothing_to_scroll_still_zooms(view, code):
    """An editor showing all of its text has no scrolling to capture."""
    code.content_widget.editor.setPlainText("one line")
    before = view.transform().m11()

    view.wheelEvent(wheel(view, inside(code)))

    assert view.transform().m11() != before


# --- staying on the grid ----------------------------------------------------


def test_every_default_size_is_grid_aligned():
    """A node that starts off-grid can never be nudged back onto it.

    Dragging only ever snaps the corner being held, so an odd starting size
    survives every resize.
    """
    from amaranth_companion.module.element.graphics_item.node_graphics_item import (
        DEFAULT_SIZE,
    )
    from amaranth_companion.module.grid import is_aligned

    for kind, size in SIZE_BY_KIND.items():
        assert all(is_aligned(value) for value in size), f"{kind} is {size}"

    assert all(is_aligned(value) for value in DEFAULT_SIZE)


def test_the_minimum_size_is_grid_aligned():
    from amaranth_companion.module.grid import is_aligned

    assert is_aligned(MIN_WIDTH)
    assert is_aligned(MIN_HEIGHT)


@pytest.mark.parametrize(
    "block_id",
    ["builtin.code", "builtin.port_in", "builtin.variable", "logic.and2"],
)
def test_a_freshly_inserted_block_is_grid_aligned(design, block_id):
    from amaranth_companion.module.grid import is_aligned

    node = design.instantiate(library().require(block_id))

    assert all(is_aligned(value) for value in node.size)


def test_resizing_snaps_to_the_grid(code):
    from amaranth_companion.module.grid import SIZE, is_aligned

    code.size = (437, 291)

    assert all(is_aligned(value) for value in code.size)
    assert code.size == (440, 300)


def test_the_scene_and_the_nodes_share_one_grid(design):
    """Two definitions would drift apart; the scene draws what nodes snap to."""
    from amaranth_companion.module.grid import SIZE

    assert design.current_module.scene.GRID_SIZE == SIZE


def test_a_size_loaded_from_a_file_is_snapped(design, code):
    """An older file, or a hand-edited one, must not reintroduce odd sizes."""
    from amaranth_companion.module.grid import is_aligned

    data = design.to_dict()
    data["nodes"][code.uuid]["size"] = [433, 287]

    restored = Design()
    restored.load(data)

    assert all(
        is_aligned(value) for value in next(iter(restored.root.nodes.values())).size
    )
