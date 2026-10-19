"""The hierarchy tree and the block palette, and drag and drop between them."""

import pytest
from PyQt5.QtCore import QMimeData, QPoint, QPointF, Qt
from PyQt5.QtGui import QDropEvent

from amaranth_companion import mime
from amaranth_companion.blocks.library import library
from amaranth_companion.design import Design
from amaranth_companion.windows.hierarchy import PATH_ROLE, HierarchyDock
from amaranth_companion.windows.main_window import MainWindow
from amaranth_companion.windows.palette import BLOCK_ROLE, BlockPalette


def rows(tree, item=None):
    """Every row in a tree, as (label, item)."""
    found = []
    count = tree.topLevelItemCount() if item is None else item.childCount()
    for index in range(count):
        child = tree.topLevelItem(index) if item is None else item.child(index)
        found.append((child.text(0), child))
        found += rows(tree, child)
    return found


@pytest.fixture
def window(qapp):
    window = MainWindow()
    yield window
    window.close()


@pytest.fixture
def gates(window):
    window.open_example("logic-gates")
    return window


# --- the hierarchy tree -----------------------------------------------------


def test_the_tree_shows_every_module(gates):
    labels = [label for label, _item in rows(gates._hierarchy.tree)]

    assert labels[0] == gates.design.name
    assert sorted(labels[1:]) == ["AND", "NOT", "OR", "XOR"]


def test_the_tree_is_empty_without_a_design(qapp):
    dock = HierarchyDock()
    dock.rebuild(None)

    assert dock.tree.topLevelItemCount() == 0


def test_the_current_module_is_selected(gates):
    gate = next(n for n in gates.current_module.nodes.values() if n.title == "OR")
    gates.enter_node(gate)

    current = gates._hierarchy.tree.currentItem()

    assert current.text(0) == "OR"
    assert current.data(0, PATH_ROLE) == [gate.uuid]


def test_clicking_a_row_steps_into_that_module(gates):
    _label, item = next(row for row in rows(gates._hierarchy.tree) if row[0] == "XOR")

    gates._hierarchy.tree.itemClicked.emit(item, 0)

    assert gates.design.breadcrumb[-1] == "XOR"
    assert gates.current_module is gates.design.current_module


def test_a_stale_row_does_not_navigate(gates):
    """Deleting a module the tree still shows must not throw."""
    gate = next(n for n in gates.current_module.nodes.values() if n.title == "NOT")
    _label, item = next(row for row in rows(gates._hierarchy.tree) if row[0] == "NOT")
    gates.current_module.remove_node(gate)

    gates._hierarchy.tree.itemClicked.emit(item, 0)

    assert gates.design.breadcrumb == [gates.design.name]


def test_rebuilding_does_not_navigate(gates):
    """Selecting the current row while rebuilding would re-enter it."""
    gate = next(n for n in gates.current_module.nodes.values() if n.title == "AND")
    gates.enter_node(gate)
    before = list(gates.design.breadcrumb)

    gates._hierarchy.rebuild(gates.design)

    assert gates.design.breadcrumb == before


def test_the_tree_follows_an_insertion(gates):
    gates.insert_block("logic.and2")

    labels = [label for label, _item in rows(gates._hierarchy.tree)]

    assert labels.count("AND") == 2


# --- the block palette ------------------------------------------------------


def test_the_palette_lists_the_library(qapp):
    palette = BlockPalette()
    ids = {
        item.data(0, BLOCK_ROLE)
        for _label, item in rows(palette.tree)
        if item.data(0, BLOCK_ROLE)
    }

    assert ids == set(library().definitions)


def test_categories_are_not_draggable(qapp):
    palette = BlockPalette()
    top = palette.tree.topLevelItem(0)

    assert top.data(0, BLOCK_ROLE) is None


def test_double_clicking_a_block_inserts_it(gates):
    before = len(gates.current_module.nodes)
    _label, item = next(
        row
        for row in rows(gates._palette.tree)
        if row[1].data(0, BLOCK_ROLE) == "builtin.code"
    )

    gates._palette.tree.itemDoubleClicked.emit(item, 0)

    assert len(gates.current_module.nodes) == before + 1


def test_double_clicking_a_category_inserts_nothing(gates):
    before = len(gates.current_module.nodes)

    gates._palette.tree.itemDoubleClicked.emit(gates._palette.tree.topLevelItem(0), 0)

    assert len(gates.current_module.nodes) == before


def test_a_block_dragged_out_carries_its_id(qapp):
    palette = BlockPalette()
    _label, item = next(
        row for row in rows(palette.tree) if row[1].data(0, BLOCK_ROLE) == "logic.not"
    )

    data = palette.tree.mimeData([item])

    assert bytes(data.data(mime.BLOCK)).decode() == "logic.not"


# --- dropping a block on the canvas -----------------------------------------


def test_a_dropped_block_lands_where_it_was_dropped(gates):
    """Off-grid by construction: the drop position has to be snapped."""
    gates.drop_block("builtin.code", QPointF(317, 462))

    node = max(gates.current_module.nodes.values(), key=lambda n: n.pos[1])

    assert node.pos == (320, 460)


def test_the_canvas_accepts_a_block_drop(gates):
    data = QMimeData()
    data.setData(mime.BLOCK, b"builtin.variable")
    before = len(gates.current_module.nodes)

    event = QDropEvent(
        QPoint(40, 40), Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier
    )
    gates._scene_view.dropEvent(event)

    assert event.isAccepted()
    assert len(gates.current_module.nodes) == before + 1


def test_the_canvas_ignores_other_drops(gates):
    data = QMimeData()
    data.setText("just some text")
    before = len(gates.current_module.nodes)

    gates._scene_view.dropEvent(
        QDropEvent(QPoint(40, 40), Qt.CopyAction, data, Qt.LeftButton, Qt.NoModifier)
    )

    assert len(gates.current_module.nodes) == before


# --- dragging a node out to delete it ---------------------------------------


def test_a_node_dropped_on_the_palette_is_deleted(gates):
    gate = next(n for n in gates.current_module.nodes.values() if n.title == "OR")
    data = QMimeData()
    data.setData(mime.NODE, gate.uuid.encode())

    event = QDropEvent(
        QPoint(10, 10), Qt.MoveAction, data, Qt.LeftButton, Qt.NoModifier
    )
    gates._palette.tree.dropEvent(event)

    assert gate.uuid not in gates.current_module.nodes
    assert event.isAccepted()


def test_deleting_a_node_is_undoable(gates):
    gate = next(n for n in gates.current_module.nodes.values() if n.title == "OR")
    gates.discard_node(gate.uuid)

    gates.undo()

    assert any(n.title == "OR" for n in gates.current_module.nodes.values())


def test_discarding_an_unknown_node_does_nothing(gates):
    before = len(gates.current_module.nodes)

    gates.discard_node("no-such-uuid")

    assert len(gates.current_module.nodes) == before


def test_the_palette_refuses_anything_but_a_node(gates):
    data = QMimeData()
    data.setText("not a node")
    before = len(gates.current_module.nodes)

    gates._palette.tree.dropEvent(
        QDropEvent(QPoint(10, 10), Qt.MoveAction, data, Qt.LeftButton, Qt.NoModifier)
    )

    assert len(gates.current_module.nodes) == before


# --- showing and hiding -----------------------------------------------------


def panels_menu(window):
    for action in window.menuBar().actions():
        if action.text() == "&View":
            for entry in action.menu().actions():
                if entry.text() == "&Panels":
                    return entry.menu()
    raise AssertionError("no Panels submenu")


def test_both_docks_can_be_hidden_from_the_menu(gates):
    gates.show()
    entries = {action.text(): action for action in panels_menu(gates).actions()}

    assert set(entries) == {"Hierarchy", "Blocks"}

    entries["Blocks"].trigger()
    assert gates._palette.isHidden()

    entries["Blocks"].trigger()
    assert not gates._palette.isHidden()
