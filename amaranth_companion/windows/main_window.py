from logging import getLogger
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QGuiApplication, QIcon, QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QToolBar,
)

from .. import __version__
from ..blocks.definition import BlockKind
from ..blocks.authoring import BlockWriteError, write_block
from ..blocks.library import block_directories, library, reload_library
from ..design import Design
from ..examples import find as find_example
from ..examples import list_examples, open_example
from ..module.element import Node
from ..module.element.graphics_item import (
    CodeContentWidget,
    EdgeGraphicsItem,
    NodeGraphicsItem,
)
from ..generate import (
    GenerationError,
    generate_files,
    identifier,
    testbench_nodes,
)
from ..verify.formal import formal_nodes
from ..module.grid import snap
from ..module.instantiate import refresh_node_ports
from ..module.scene import ModuleSceneView
from ..module.serialization import (
    dumps,
    internal_edges,
    loads,
    selection_to_dict,
)
from ..theme import ThemeMode, theme_manager
from .. import platforms
from ..verify import (
    ViewerMissing,
    run_build,
    open_viewer,
    run_formal,
    run_testbench,
    run_waveform,
    viewer_available,
)
from .hierarchy import HierarchyDock
from .icons import themed_icon
from .palette import BlockPalette
from .actions import (
    ACTIONS,
    BOARDS_MENU,
    EXAMPLES_MENU,
    PANELS_MENU,
    INSERT_MENU,
    MENUS,
    SEPARATOR,
    THEME_ACTIONS,
    TOOLBARS,
    SubmenuSpec,
)

log = getLogger(__name__)

FILE_FILTER = "Graph (*.json);;All files (*)"

#: how long after the last keystroke a block's ports are re-derived.
#: Introspection spawns an interpreter, so it must not run per character.
PORT_REFRESH_DELAY_MS = 500

#: clock cycles a Simulate run covers unless the user says otherwise
DEFAULT_SIMULATION_CLOCKS = 100
MAX_SIMULATION_CLOCKS = 1_000_000

#: fraction of the available screen the window covers when it has no better
#: idea, clamped to DEFAULT_MAX_SIZE so it does not span an ultrawide desktop
DEFAULT_SCREEN_FRACTION = 0.8
DEFAULT_MAX_SIZE = (1600, 1000)
MINIMUM_SIZE = (800, 560)


class MainWindow(QMainWindow):
    """Main Window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Amaranth Companion")

        self._design: Design | None = None
        self._scene_view: ModuleSceneView | None = None
        self._action_groups: dict[str, QActionGroup] = {}
        self._breadcrumb_bar: QToolBar | None = None
        self._boards_menu: QMenu | None = None
        self._board_group: QActionGroup | None = None
        self._hierarchy: HierarchyDock | None = None
        self._palette: BlockPalette | None = None

        #: coalesces keystrokes into one introspection run per node
        #: remembered between Simulate runs, so the usual answer is one click
        self._simulation_clocks = DEFAULT_SIMULATION_CLOCKS

        self._pending_refresh: set[Node] = set()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(PORT_REFRESH_DELAY_MS)
        self._refresh_timer.timeout.connect(self._run_pending_refreshes)

        self._create_actions()
        theme_manager().changed.connect(self._retheme_icons)
        # before the menu bar, which offers the docks' own toggle actions
        self._create_docks()
        self._create_menu_bar()
        self._create_tool_bars()
        self._create_breadcrumb_bar()
        self._create_status_bar()
        self._sync_theme_actions()
        self._set_default_geometry()

    # --- construction ------------------------------------------------------

    def _create_actions(self) -> None:
        for spec in ACTIONS:
            action = QAction(spec.text, self)
            if spec.icon:
                action.setIcon(themed_icon(spec.icon))
            if spec.shortcuts:
                action.setShortcuts([QKeySequence(s) for s in spec.shortcuts])
            if spec.tip:
                action.setStatusTip(spec.tip)
                action.setToolTip(spec.tip)
            if spec.checkable:
                action.setCheckable(True)
            if spec.group:
                self._action_group(spec.group).addAction(action)
            action.triggered.connect(getattr(self, spec.slot))
            setattr(self, self._action_attr(spec.name), action)

    def _retheme_icons(self) -> None:
        """Redraw the icons; black line art vanishes on a dark toolbar."""
        for spec in ACTIONS:
            if spec.icon:
                self._action(spec.name).setIcon(themed_icon(spec.icon))

    def _action_group(self, name: str) -> QActionGroup:
        group = self._action_groups.get(name)
        if group is None:
            group = QActionGroup(self)
            group.setExclusive(True)
            self._action_groups[name] = group
        return group

    @staticmethod
    def _action_attr(name: str) -> str:
        return f"{name}_action"

    def _action(self, name: str) -> QAction:
        return getattr(self, self._action_attr(name))

    def _create_menu_bar(self) -> None:
        menu_bar = QMenuBar(self)

        for title, entries in MENUS:
            menu = menu_bar.addMenu(title)
            for entry in entries:
                if entry is SEPARATOR:
                    menu.addSeparator()
                elif entry is INSERT_MENU:
                    self._build_insert_menu(menu)
                elif entry is EXAMPLES_MENU:
                    self._build_examples_menu(menu)
                elif entry is BOARDS_MENU:
                    self._build_boards_menu(menu)
                elif entry is PANELS_MENU:
                    self._build_panels_menu(menu)
                elif isinstance(entry, SubmenuSpec):
                    self._add_submenu(menu, entry)
                else:
                    menu.addAction(self._action(entry))

        self.setMenuBar(menu_bar)

    def _add_submenu(self, parent: QMenu, spec: SubmenuSpec) -> None:
        submenu = parent.addMenu(spec.title)
        for name in spec.entries:
            submenu.addAction(self._action(name))
        for text in spec.placeholders:
            submenu.addAction(text).setEnabled(False)

    def _build_insert_menu(self, menu: QMenu) -> None:
        """One entry per block definition, grouped by its category path.

        Generated from the library rather than listed in ``actions.py``, so a
        block definition dropped into the blocks directory shows up without
        any code change -- which is the point of keeping blocks as data.
        """
        menu.clear()

        for category, definitions in library().by_category().items():
            target = menu
            for level in category:
                target = self._submenu_named(target, level)
            for definition in definitions:
                action = target.addAction(definition.label)
                action.setStatusTip(definition.doc or definition.id)
                action.setData(definition.id)
                action.triggered.connect(
                    lambda _checked=False, block_id=definition.id: self.insert_block(
                        block_id
                    )
                )

    def _build_panels_menu(self, parent: QMenu) -> None:
        """Show and hide the docks.

        Qt's own ``toggleViewAction`` would have done, but it reports where a
        dock *is* rather than where the user wants it, and the panels are
        taken off screen whenever no design is open.
        """
        submenu = parent.addMenu("&Panels")
        for dock in self._docks:
            action = submenu.addAction(dock.windowTitle())
            action.setCheckable(True)
            action.setChecked(self._panel_wanted[dock])
            action.toggled.connect(
                lambda checked, dock=dock: self._set_panel_wanted(dock, checked)
            )

    def _build_boards_menu(self, parent: QMenu) -> None:
        """One entry per platform installed, grouped by the package it came from.

        Generated from what is importable rather than a bundled list: the
        boards come from ``amaranth-boards`` and ``glasgow``, and a design can
        only be built for what this machine actually has.
        """
        submenu = parent.addMenu("&Board")
        self._boards_menu = submenu
        available = platforms.list_platforms()

        none_action = submenu.addAction("None (simulation only)")
        none_action.setCheckable(True)
        self._board_group = self._action_group("board")
        self._board_group.addAction(none_action)
        none_action.triggered.connect(lambda: self.set_platform(None))

        if not available:
            submenu.addAction("No board packages installed").setEnabled(False)
            return

        submenu.addSeparator()
        by_vendor: dict[str, QMenu] = {}

        for spec in available:
            vendor = by_vendor.get(spec.vendor)
            if vendor is None:
                vendor = submenu.addMenu(spec.vendor.replace("_", "-"))
                by_vendor[spec.vendor] = vendor

            action = vendor.addAction(spec.label)
            action.setCheckable(True)
            action.setData(spec.id)
            action.setStatusTip(spec.id)
            self._board_group.addAction(action)
            action.triggered.connect(
                lambda _checked=False, chosen=spec.id: self.set_platform(chosen)
            )

    def set_platform(self, platform_id: str | None) -> None:
        """Choose the board this design is built for."""
        if self._design is None:
            return

        self._design.platform = platform_id
        self._design.history.check_in()
        self._sync_board_actions()
        self._refresh_resource_blocks()

        spec = platforms.find(platform_id) if platform_id else None
        self.statusbar.showMessage(
            f"Building for {spec.label}" if spec else "No board; simulation only",
            5000,
        )

    def _sync_board_actions(self) -> None:
        chosen = self._design.platform if self._design else None
        for action in self._board_group.actions():
            action.setChecked(action.data() == chosen)

    def _refresh_resource_blocks(self) -> None:
        """Re-offer the board's ios, and re-derive what each block binds to."""
        if self._design is None:
            return

        choices = (
            [spec.id for spec in platforms.list_ios(self._design.platform)]
            if self._design.platform
            else []
        )

        for module in self._design.walk():
            for node in module.nodes.values():
                if node.kind is not BlockKind.RESOURCE:
                    continue
                widget = node.content_widget
                if hasattr(widget, "set_choices"):
                    widget.set_choices(choices)
                self._refresh_one(node)

    def _build_examples_menu(self, parent: QMenu) -> None:
        """One entry per shipped design, from the examples index."""
        submenu = parent.addMenu("Open &Example")
        examples = list_examples()

        if not examples:
            submenu.addAction("No examples installed").setEnabled(False)
            return

        for example in examples:
            action = submenu.addAction(example.label)
            action.setStatusTip(example.doc or example.name)
            action.setToolTip(example.doc or example.name)
            action.triggered.connect(
                lambda _checked=False, name=example.name: self.open_example(name)
            )

    @staticmethod
    def _submenu_named(parent: QMenu, title: str) -> QMenu:
        """``parent``'s submenu called ``title``, created if it is not there."""
        for action in parent.actions():
            if action.menu() is not None and action.text() == title:
                return action.menu()
        return parent.addMenu(title)

    def _create_tool_bars(self) -> None:
        for title, names in TOOLBARS:
            tool_bar = QToolBar(title, self)
            tool_bar.setMovable(False)
            for name in names:
                tool_bar.addAction(self._action(name))
            self.addToolBar(tool_bar)

    def _create_status_bar(self) -> None:
        self.statusbar = self.statusBar()
        self.statusbar.showMessage("Ready", 3000)

    def _set_default_geometry(self) -> None:
        """Open large enough to show a node graph, and centred.

        Without this the window is sized to its menu bar and toolbars, which
        leaves barely any canvas.
        """
        self.setMinimumSize(*MINIMUM_SIZE)

        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(*DEFAULT_MAX_SIZE)
            return

        available = screen.availableGeometry()
        width = min(
            int(available.width() * DEFAULT_SCREEN_FRACTION), DEFAULT_MAX_SIZE[0]
        )
        height = min(
            int(available.height() * DEFAULT_SCREEN_FRACTION), DEFAULT_MAX_SIZE[1]
        )
        width = max(width, MINIMUM_SIZE[0])
        height = max(height, MINIMUM_SIZE[1])

        self.resize(width, height)
        self.move(
            available.x() + (available.width() - width) // 2,
            available.y() + (available.height() - height) // 2,
        )

    # --- document ----------------------------------------------------------

    @property
    def design(self) -> Design | None:
        return self._design

    @property
    def current_module(self):
        """The graph on screen, which is a child graph when descended into."""
        return self._design.current_module if self._design else None

    @property
    def current_view(self) -> ModuleSceneView | None:
        return self._scene_view

    def open_design(self, design: Design) -> None:
        self._design = design

        if self._scene_view is None:
            self._scene_view = ModuleSceneView()
            self._scene_view.node_activated.connect(self.enter_node)
            self._scene_view.block_dropped.connect(self.drop_block)
            self.setCentralWidget(self._scene_view)

        self._show_current_module()
        self._sync_board_actions()
        self._refresh_resource_blocks()

        # a design laid out wider than the window would open showing a corner
        # of itself. Deferred by one turn of the event loop: the view has no
        # usable size until it has been laid out, and fitting against a stale
        # viewport zooms out much too far.
        QTimer.singleShot(0, self._fit_view)

    def build_design(self, program: bool = False) -> None:
        """Synthesise the design for its board, and optionally load it on."""
        if self._design is None:
            return

        if not self._design.platform:
            self.statusbar.showMessage("Choose a board first: Build -> Board", 8000)
            return

        verb = "Building and programming" if program else "Building"
        self.statusbar.showMessage(f"{verb}... this takes a while")

        result = run_build(self._design, program=program)

        if result.ok and not result.error:
            self.statusbar.showMessage(f"{result.summary} in {result.build_dir}", 20000)
        else:
            # a bitstream that built but could not be loaded on is a failure
            # of what was asked for, even though there is a bitstream
            self._report(result.summary, RuntimeError(result.error))

    def program_design(self) -> None:
        self.build_design(program=True)

    def _fit_view(self) -> None:
        if self._scene_view is not None:
            self._scene_view.fit_contents()

    def close_design(self) -> None:
        self._design = None
        self._pending_refresh.clear()

        if self._scene_view is not None:
            self._scene_view.setScene(None)
            # QMainWindow takes ownership, so the old view is destroyed here
            self.setCentralWidget(None)
            self._scene_view = None

        self._update_breadcrumb()
        self._update_hierarchy()
        self._update_docks()
        self.setWindowTitle("Amaranth Companion")

    def _show_current_module(self) -> None:
        """Point the view at whichever level of the hierarchy is current."""
        if self._design is None or self._scene_view is None:
            return

        module = self._design.current_module
        self._scene_view.module = module
        self._connect_content_widgets(module)
        self._follow_renames(module)
        self._update_breadcrumb()
        self._update_hierarchy()
        self._update_docks()
        self.setWindowTitle(
            f"{' / '.join(self._design.breadcrumb)} - Amaranth Companion"
        )

    # --- hierarchy navigation ----------------------------------------------

    def _create_breadcrumb_bar(self) -> None:
        self.addToolBarBreak()
        self._breadcrumb_bar = QToolBar("Location", self)
        self._breadcrumb_bar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, self._breadcrumb_bar)
        self._update_breadcrumb()

    def _create_docks(self) -> None:
        """The tree on the left, the blocks on the right."""
        self._hierarchy = HierarchyDock(self)
        self._hierarchy.module_chosen.connect(self.go_to_path)
        self.addDockWidget(Qt.LeftDockWidgetArea, self._hierarchy)

        self._palette = BlockPalette(self)
        self._palette.block_chosen.connect(self.insert_block)
        self._palette.node_discarded.connect(self.discard_node)
        self.addDockWidget(Qt.RightDockWidgetArea, self._palette)

        self._docks = (self._hierarchy, self._palette)
        # whether the user wants each panel, which is not the same as whether
        # it is on screen: with no design open there is nothing to show either
        # of them, but closing a design must not forget the choice
        self._panel_wanted = {dock: True for dock in self._docks}
        self._update_docks()

    def _update_docks(self) -> None:
        """Show the panels only while a design is open."""
        open_design = self._design is not None
        for dock in getattr(self, "_docks", ()):
            dock.setVisible(open_design and self._panel_wanted[dock])

    def _set_panel_wanted(self, dock, wanted: bool) -> None:
        self._panel_wanted[dock] = wanted
        self._update_docks()

    def go_to_path(self, path) -> None:
        """Jump to any module in the tree, as the hierarchy view offers."""
        if self._design is None or not self._design.go_to_path(path):
            return
        self._show_current_module()

    def discard_node(self, uuid: str) -> None:
        """Delete the node dragged out onto the palette."""
        module = self.current_module
        node = module.nodes.get(uuid) if module else None
        if node is None:
            return

        title = node.title
        module.remove_node(node)
        module.history.check_in()
        self._show_current_module()
        self.statusbar.showMessage(f"Deleted {title}", 5000)

    def _follow_renames(self, module) -> None:
        """Hear about renames in ``module``, without hearing about them twice.

        A module keeps its scene, so coming back to one would otherwise stack
        up another connection each time.
        """
        try:
            module.scene.node_renamed.disconnect(self._node_renamed)
        except TypeError:
            pass
        module.scene.node_renamed.connect(self._node_renamed)

    def _node_renamed(self, node: Node) -> None:
        """A block's new title is the name it goes by in the tree."""
        self._update_hierarchy()
        self.statusbar.showMessage(f"Renamed to {node.title}", 3000)

    def _update_hierarchy(self) -> None:
        if self._hierarchy is not None:
            self._hierarchy.rebuild(self._design)

    def _update_breadcrumb(self) -> None:
        """Rebuild the path bar: one clickable entry per level descended."""
        if self._breadcrumb_bar is None:
            return

        self._breadcrumb_bar.clear()

        if self._design is None:
            self._breadcrumb_bar.setVisible(False)
            return

        # shown even at the root, where it is one entry naming the design:
        # a bar that comes and goes shifts the canvas under the pointer
        self._breadcrumb_bar.setVisible(True)
        labels = self._design.breadcrumb

        for depth, label in enumerate(labels):
            if depth:
                self._breadcrumb_bar.addWidget(QLabel("  /  "))
            action = self._breadcrumb_bar.addAction(label)
            action.setEnabled(depth < len(labels) - 1)
            action.triggered.connect(
                lambda _checked=False, target=depth: self.go_to_depth(target)
            )

    def enter_node(self, node: Node) -> None:
        """Descend into a hierarchical block."""
        if self._design is None or not self._design.enter(node):
            return

        self._show_current_module()
        self.statusbar.showMessage(f"Entered {node.title}", 3000)

    def go_up(self) -> None:
        if self._design is not None and self._design.leave():
            self._show_current_module()

    def go_to_depth(self, depth: int) -> None:
        if self._design is None:
            return
        self._design.go_to_depth(depth)
        self._show_current_module()

    # --- blocks -------------------------------------------------------------

    def insert_block(self, block_id: str, pos=None) -> None:
        """Place a block from the library, by default at the centre of the view."""
        if self._design is None:
            self.new_file()

        definition = library().get(block_id)
        if definition is None:
            self._report(f"Unknown block {block_id}", KeyError(block_id))
            return

        node = self._design.instantiate(
            definition, pos=pos if pos is not None else self._insert_position()
        )
        self._connect_content_widget(node)
        self.current_module.history.check_in()
        self._update_hierarchy()

        message = f"Inserted {definition.label}"
        if node.error:
            message = f"{message} ({node.error})"
        self.statusbar.showMessage(message, 5000)

    def drop_block(self, block_id: str, position) -> None:
        """Place a block where it was dropped, rather than mid-view."""
        self.insert_block(block_id, (snap(position.x()), snap(position.y())))

    def _insert_position(self) -> tuple[float, float]:
        """The middle of what the user is looking at, snapped to the grid."""
        if self._scene_view is None:
            return 0.0, 0.0

        centre = self._scene_view.mapToScene(
            self._scene_view.viewport().rect().center()
        )
        return snap(centre.x()), snap(centre.y())

    def _connect_content_widgets(self, module) -> None:
        for node in module.nodes.values():
            self._connect_content_widget(node)

    def _connect_content_widget(self, node: Node) -> None:
        """Have a node ask for a port refresh when its content changes."""
        widget = node.content_widget
        try:
            widget.content_changed.disconnect()
        except TypeError:
            pass  # nothing was connected yet
        widget.content_changed.connect(lambda bound=node: self._schedule_refresh(bound))

    def _schedule_refresh(self, node: Node) -> None:
        self._pending_refresh.add(node)
        self._refresh_timer.start()

    def _run_pending_refreshes(self) -> None:
        nodes, self._pending_refresh = self._pending_refresh, set()
        for node in nodes:
            self._refresh_one(node)

    def _refresh_one(self, node: Node) -> None:
        diff, error = refresh_node_ports(node)

        # duck-typed: code blocks and resource blocks both report, and a
        # port block has nowhere to put a message
        widget = node.content_widget
        if hasattr(widget, "show_error"):
            widget.show_error(error, node.error_line)

        # a port block renaming itself changes the enclosing block's interface
        if node.kind.is_port:
            self._refresh_enclosing_block()

        if diff.changed:
            self.statusbar.showMessage(f"{node.title}: {diff.describe()}", 5000)
            self.current_module.history.check_in()

    def _refresh_enclosing_block(self) -> None:
        """Re-derive the ports of the block whose implementation is on screen."""
        if self._design is None:
            return

        stack = self._design.stack
        if stack:
            self._refresh_one_shallow(stack[-1])

    def _refresh_one_shallow(self, node: Node) -> None:
        diff, _error = refresh_node_ports(node)
        if diff.changed:
            self.statusbar.showMessage(f"{node.title}: {diff.describe()}", 5000)

    def refresh_ports(self) -> None:
        """Re-read the ports of the selected blocks, or of all of them."""
        module = self.current_module
        if module is None:
            return

        selected = [
            item.node
            for item in self._scene_view.scene().selectedItems()
            if isinstance(item, NodeGraphicsItem)
        ]
        for node in selected or list(module.nodes.values()):
            self._refresh_one(node)

    # --- file actions ------------------------------------------------------

    def new_file(self) -> None:
        """Start an empty design.

        No placeholder nodes: the Insert menu is how blocks get onto a canvas
        now, and three unnamed demo blocks were only ever scaffolding.
        """
        self.open_design(Design())
        self.statusbar.showMessage("New design", 3000)

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open graph from file", "", FILE_FILTER
        )
        if not path:
            return

        try:
            design = Design.from_file(path)
        except (OSError, ValueError, KeyError) as error:
            self._report(f"Could not open {path}", error)
            return

        self.open_design(design)
        self.statusbar.showMessage(f"Opened {path}", 5000)

    def open_example(self, name: str) -> None:
        """Open one of the shipped designs as a new untitled document."""
        example = find_example(name)
        if example is None:
            self._report(f"No example called {name}", KeyError(name))
            return

        try:
            design = open_example(example)
        except (OSError, ValueError, KeyError) as error:
            self._report(f"Could not open the {example.label} example", error)
            return

        self.open_design(design)
        self.statusbar.showMessage(f"Opened the {example.label} example", 5000)

    def save_file(self) -> None:
        if self._design is None:
            return

        if self._design.path is None:
            self.save_as_file()
        else:
            self._save(self._design.path)

    def save_as_file(self) -> None:
        if self._design is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save graph to file", "", FILE_FILTER
        )
        if path:
            self._save(path)

    def _save(self, path: str) -> None:
        try:
            self._design.save(path)
        except OSError as error:
            self._report(f"Could not save to {path}", error)
            return

        self._show_current_module()
        self.statusbar.showMessage(f"Saved as {path}", 5000)

    def close_file(self) -> None:
        self.close_design()

    def export_design(self) -> None:
        """Write the design out as an amaranth package."""
        if self._design is None:
            return

        directory = QFileDialog.getExistingDirectory(
            self, "Export amaranth package to", ""
        )
        if not directory:
            return

        package = identifier(self._design.name, "design")

        try:
            files = generate_files(self._design, package)
        except GenerationError as error:
            self._report("Could not generate the design", error)
            return

        try:
            written = self._write_files(Path(directory), files)
        except OSError as error:
            self._report(f"Could not write to {directory}", error)
            return

        self.statusbar.showMessage(
            f"Exported {len(written)} files to {directory}/{package}", 8000
        )

    # --- verification ------------------------------------------------------

    def run_tests(self) -> None:
        """Run every testbench and formal block, reporting on the blocks."""
        if self._design is None:
            return

        benches = testbench_nodes(self._design)
        proofs = formal_nodes(self._design)
        if not benches and not proofs:
            self.statusbar.showMessage("Nothing to check in this design", 5000)
            return

        self.statusbar.showMessage(f"Checking {len(benches) + len(proofs)} blocks...")

        passed = failed = skipped = 0

        for node in benches:
            result = run_testbench(self._design, node)
            passed, failed = (passed + 1, failed) if result.ok else (passed, failed + 1)
            self._show_result(node, result)

        for node in proofs:
            # one result per mode, collapsed onto the one block
            results = run_formal(self._design, node)
            skipped += sum(1 for result in results if result.skipped)
            passed += sum(1 for result in results if result.ok)
            failed += sum(
                1 for result in results if not result.ok and not result.skipped
            )
            self._show_result(node, self._worst(results))

        self.statusbar.showMessage(self._summary(passed, failed, skipped), 15000)

    def simulate_design(self) -> None:
        """Run the design for a while and open the waveform viewer."""
        if self._design is None:
            return

        clocks, confirmed = QInputDialog.getInt(
            self,
            "Simulate",
            "Clock cycles to run:",
            self._simulation_clocks,
            1,
            MAX_SIMULATION_CLOCKS,
        )
        if not confirmed:
            return

        self._simulation_clocks = clocks
        self.statusbar.showMessage(f"Simulating {clocks} clocks...")

        result = run_waveform(self._design, clocks=clocks)
        if not result.ok:
            self._report("Simulation failed", RuntimeError(result.error))
            return

        self.statusbar.showMessage(result.summary, 10000)
        self._open_waveform(result)

    def _open_waveform(self, result) -> None:
        if not viewer_available():
            self.statusbar.showMessage(
                f"{result.summary} - install gtkwave to view it", 15000
            )
            return

        try:
            open_viewer(result.vcd_path, result.gtkw_path)
        except (ViewerMissing, OSError) as error:
            self._report("Could not open the waveform viewer", error)

    @staticmethod
    def _worst(results: list):
        """The result a block should display: the first real failure, if any."""
        for result in results:
            if not result.ok and not result.skipped:
                return result
        return results[0] if results else None

    @staticmethod
    def _summary(passed: int, failed: int, skipped: int) -> str:
        parts = [f"{passed} passed"]
        if failed:
            parts.append(f"{failed} failed")
        if skipped:
            parts.append(f"{skipped} skipped (sby and yosys not on PATH)")
        return ", ".join(parts)

    @staticmethod
    def _show_result(node: Node, result) -> None:
        if result is None:
            return

        message = "" if result.ok else result.error
        node.set_error(message, None if result.ok else result.line)

        widget = node.content_widget
        if hasattr(widget, "show_error"):
            widget.show_error(message, node.error_line)

    # --- edit actions ------------------------------------------------------

    def copy_content(self) -> None:
        view = self.current_view
        if view is None:
            return

        selected = view.scene().selectedItems()
        nodes = [item.node for item in selected if isinstance(item, NodeGraphicsItem)]
        edges = [
            item.edge
            for item in selected
            if isinstance(item, EdgeGraphicsItem) and item.edge is not None
        ]

        # an edge with an endpoint outside the selection cannot be pasted, so
        # drop it from the payload and from the selection shown to the user
        copyable = internal_edges(nodes, edges)
        for edge in edges:
            if edge not in copyable:
                edge.graphics_item.setSelected(False)

        text = dumps(selection_to_dict(nodes, copyable))
        QGuiApplication.clipboard().setText(text)

    def paste_content(self) -> None:
        module = self.current_module
        if module is None:
            return

        try:
            data = loads(QGuiApplication.clipboard().text())
            module.paste(data)
        except (ValueError, KeyError, TypeError) as error:
            self._report("Clipboard does not contain a module selection", error)
            return

        module.history.check_in()

    def cut_content(self) -> None:
        view = self.current_view
        if view is None:
            return

        self.copy_content()
        view.delete_selected()

    def create_block_from_module(self) -> None:
        """Save what is on this canvas as a reusable block.

        Writes the same definition-plus-module pair the shipped gates use --
        there is nothing privileged about a built-in block.
        """
        module = self.current_module
        if module is None or not module.nodes:
            self.statusbar.showMessage("Nothing on this canvas to save", 5000)
            return

        label, confirmed = QInputDialog.getText(
            self, "Create Block", "Name for the block:", text=self._block_label()
        )
        if not confirmed or not label.strip():
            return

        category, confirmed = QInputDialog.getText(
            self, "Create Block", "Category it appears under:", text="Blocks"
        )
        if not confirmed:
            return

        # beside the design when it has been saved, so a project can carry
        # its own blocks; otherwise the shared directory
        directory = block_directories(self._design)[0]

        try:
            path = write_block(
                module,
                label=label.strip(),
                directory=directory,
                category=[part.strip() for part in category.split("/") if part.strip()],
            )
        except (BlockWriteError, OSError) as error:
            self._report("Could not create the block", error)
            return

        reload_library(self._design)
        self._rebuild_insert_menu()
        if self._palette is not None:
            self._palette.rebuild()
        self.statusbar.showMessage(f"Created {path.name} in {directory}", 10000)

    def _block_label(self) -> str:
        """A sensible default name: what the user is looking at."""
        stack = self._design.stack if self._design else []
        return stack[-1].title if stack else self._design.name if self._design else ""

    def _rebuild_insert_menu(self) -> None:
        for action in self.menuBar().actions():
            if action.text() == "&Insert" and action.menu() is not None:
                menu = action.menu()
                menu.clear()
                self._build_insert_menu(menu)
                menu.addSeparator()
                menu.addAction(self._action("create_block"))
                return

    def rename_node(self) -> None:
        """Start editing the title of the one selected block."""
        view = self.current_view
        if view is None:
            return

        selected = [
            item
            for item in view.scene().selectedItems()
            if isinstance(item, NodeGraphicsItem)
        ]

        if len(selected) != 1:
            self.statusbar.showMessage("Select a single block to rename", 5000)
            return

        selected[0].begin_rename()

    def undo(self) -> None:
        if self._design is None:
            return
        self._design.history.undo()
        # the restore rebuilt every node, so the view and the signal
        # connections have to be pointed at the new objects
        self._show_current_module()

    def redo(self) -> None:
        if self._design is None:
            return
        self._design.history.redo()
        self._show_current_module()

    # --- view actions ------------------------------------------------------

    def zoom_in(self) -> None:
        if self.current_view is not None:
            self.current_view.zoom_in_out(1)

    def zoom_out(self) -> None:
        if self.current_view is not None:
            self.current_view.zoom_in_out(-1)

    def use_theme_auto(self) -> None:
        self.set_theme(ThemeMode.AUTO)

    def use_theme_light(self) -> None:
        self.set_theme(ThemeMode.LIGHT)

    def use_theme_dark(self) -> None:
        self.set_theme(ThemeMode.DARK)

    def set_theme(self, mode: ThemeMode) -> None:
        theme = theme_manager().apply(mode)
        self._sync_theme_actions()
        self.statusbar.showMessage(f"Theme: {mode.value} ({theme.name})", 3000)

    def _sync_theme_actions(self) -> None:
        active = theme_manager().mode
        for mode, name in THEME_ACTIONS.items():
            self._action(name).setChecked(mode is active)

    # --- help actions ------------------------------------------------------

    def help_content(self) -> None:
        # TODO: ship user documentation and open it here
        self.statusbar.showMessage("Help is not available yet", 3000)

    def about(self) -> None:
        QMessageBox.about(
            self,
            "About Amaranth Companion",
            f"<b>Amaranth Companion</b> {__version__}"
            "<p>Visual editor for gateware based on amaranth-lang.</p>",
        )

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _write_files(root: Path, files: dict) -> list[str]:
        written = []
        for name, content in sorted(files.items()):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            written.append(name)
        return written

    def _report(self, message: str, error: Exception) -> None:
        log.warning("%s: %s", message, error)
        self.statusbar.showMessage(message, 5000)
