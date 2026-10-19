"""The editor window: inserting blocks, descending into them, port refresh."""

import pytest

from PyQt5.QtCore import QSettings

from amaranth_companion import theme as theme_module
from amaranth_companion.blocks.definition import BlockKind
from amaranth_companion.windows.main_window import MainWindow


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    """A window whose settings go to a throwaway file."""
    monkeypatch.setattr(
        theme_module.ThemeManager,
        "settings",
        staticmethod(
            lambda: QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
        ),
    )
    window = MainWindow()
    window.new_file()
    return window


def nodes_of(window):
    return list(window.current_module.nodes.values())


def port_node(module, name):
    return next(n for n in module.nodes.values() if n.kind.is_port and n.text == name)


# --- inserting --------------------------------------------------------------


def test_a_new_design_starts_empty(window):
    assert window.current_module.nodes == {}
    assert window.design.depth == 0


def test_the_insert_menu_offers_the_library(window):
    insert = next(
        action.menu()
        for action in window.menuBar().actions()
        if action.text() == "&Insert"
    )
    categories = [a.text() for a in insert.actions() if a.menu() is not None]

    assert "Logic" in categories


def test_inserting_a_gate_places_it(window):
    window.insert_block("logic.and2")

    node = nodes_of(window)[0]
    assert node.title == "AND"
    assert [s.name for s in node.sockets] == ["a_in", "b_in", "width_param", "o_out"]


def test_inserting_an_unknown_block_is_reported_not_raised(window):
    window.insert_block("nope.missing")

    assert window.current_module.nodes == {}


def test_inserting_is_undoable(window):
    window.insert_block("logic.and2")

    window.undo()

    assert window.current_module.nodes == {}


# --- descending -------------------------------------------------------------


def test_entering_a_gate_shows_its_implementation(window):
    window.insert_block("logic.and2")
    gate = nodes_of(window)[0]

    window.enter_node(gate)

    assert window.design.breadcrumb == ["untitled", "AND"]
    assert len(window.current_module.nodes) == 5


def test_the_view_follows_the_current_level(window):
    window.insert_block("logic.and2")
    gate = nodes_of(window)[0]

    window.enter_node(gate)

    assert window.current_view.module is gate.child_module
    assert window.current_view.scene() is gate.child_module.scene


def test_going_up_returns_to_the_root(window):
    window.insert_block("logic.and2")
    window.enter_node(nodes_of(window)[0])

    window.go_up()

    assert window.design.depth == 0
    assert window.current_module is window.design.root


def test_the_breadcrumb_hides_at_the_root(window):
    assert not window._breadcrumb_bar.isVisible()


def test_a_plain_block_is_not_enterable(window):
    window.insert_block("builtin.code")

    window.enter_node(nodes_of(window)[0])

    assert window.design.depth == 0


# --- port refresh through the window ----------------------------------------


def test_editing_a_port_block_updates_the_enclosing_gate(window):
    window.insert_block("logic.and2")
    gate = nodes_of(window)[0]
    window.enter_node(gate)

    port_node(window.current_module, "a").text = "enable"
    window._run_pending_refreshes()

    assert [s.name for s in gate.sockets] == [
        "enable_in",
        "b_in",
        "width_param",
        "o_out",
    ]


def test_a_content_change_is_debounced(window):
    """Introspection spawns an interpreter; it must not run per keystroke."""
    window.insert_block("builtin.code")
    node = nodes_of(window)[0]

    node.content_widget.text = "x = 1"

    assert node in window._pending_refresh
    assert window._refresh_timer.isActive()


def test_refresh_ports_reads_the_code(window):
    window.insert_block("builtin.code")
    node = nodes_of(window)[0]
    node.content_widget.text = (
        "from amaranth import *\n"
        "\n"
        "class Gate(Elaboratable):\n"
        "    def __init__(self):\n"
        "        self.q_in = Signal(4)\n"
        "        self.r_out = Signal(4)\n"
        "    def elaborate(self, platform):\n"
        "        return Module()\n"
    )
    window._pending_refresh.clear()

    window.refresh_ports()

    assert [s.name for s in node.sockets] == ["q_in", "r_out"]


def test_a_broken_block_shows_its_error(window):
    window.insert_block("builtin.code")
    node = nodes_of(window)[0]
    node.content_widget.text = "class Broken(:\n"

    window._run_pending_refreshes()

    assert "SyntaxError" in node.error
    assert node.content_widget.status.isVisible()


# --- files ------------------------------------------------------------------


def test_saving_and_reopening_a_hierarchy(window, tmp_path):
    window.insert_block("logic.and2")
    path = tmp_path / "design.json"
    window.design.save(path)

    reopened = MainWindow()
    from amaranth_companion.design import Design

    reopened.open_design(Design.from_file(path))

    gate = list(reopened.current_module.nodes.values())[0]
    assert gate.child_module is not None
    assert [s.name for s in gate.sockets] == ["a_in", "b_in", "width_param", "o_out"]


def test_closing_clears_the_canvas(window):
    window.insert_block("logic.and2")

    window.close_file()

    assert window.design is None
    assert window.current_view is None


# --- the run toolbar --------------------------------------------------------


def toolbar_named(window, title):
    from PyQt5.QtWidgets import QToolBar

    return next(
        bar for bar in window.findChildren(QToolBar) if bar.windowTitle() == title
    )


def test_there_is_a_toolbar_for_running_things(window):
    bar = toolbar_named(window, "Run")

    assert [action.text() for action in bar.actions()] == [
        "&Run Tests",
        "&Simulate...",
        "&Build Bitstream",
    ]


def test_the_run_actions_have_icons(window):
    for name in ("run_tests", "simulate", "build"):
        assert not window._action(name).icon().isNull()


def test_icons_are_redrawn_for_the_theme(window):
    """Black line art is invisible on a dark toolbar."""
    from amaranth_companion.theme import ThemeMode, theme_manager
    from amaranth_companion.windows.icons import themed_icon

    mode = theme_manager().mode
    try:
        theme_manager().apply(ThemeMode.LIGHT, persist=False)
        light = themed_icon(":test.svg").pixmap(16, 16).toImage()
        theme_manager().apply(ThemeMode.DARK, persist=False)
        dark = themed_icon(":test.svg").pixmap(16, 16).toImage()
    finally:
        theme_manager().apply(mode, persist=False)

    assert light != dark


def test_a_missing_icon_does_not_raise(qapp):
    from amaranth_companion.windows.icons import themed_icon

    assert themed_icon(":nowhere.svg") is not None


def test_renaming_needs_a_single_selection(window):
    window.insert_block("logic.and2")
    window.insert_block("logic.not")
    for node in window.current_module.nodes.values():
        node.graphics_item.setSelected(True)

    window.rename_node()

    assert not any(
        node.graphics_item.title_item.editing
        for node in window.current_module.nodes.values()
    )


def test_renaming_the_selected_block_starts_editing(window):
    window.insert_block("logic.and2")
    node = nodes_of(window)[0]
    node.graphics_item.setSelected(True)

    window.rename_node()

    assert node.graphics_item.title_item.editing
