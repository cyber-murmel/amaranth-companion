from logging import getLogger

from PyQt5.QtGui import QGuiApplication, QIcon, QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QFileDialog,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QToolBar,
)

from .. import __version__
from ..module import Module
from ..module.element import Edge, Node, SocketType
from ..module.element.graphics_item import (
    EdgeGraphicsItem,
    NodeContentWidget,
    NodeGraphicsItem,
)
from ..module.scene import ModuleSceneView
from ..module.serialization import (
    dumps,
    internal_edges,
    loads,
    selection_to_dict,
)
from .actions import ACTIONS, MENUS, SEPARATOR, TOOLBARS, SubmenuSpec

log = getLogger(__name__)

FILE_FILTER = "Graph (*.json);;All files (*)"

#: socket layout of the placeholder nodes created by "New"
DEMO_INPUTS = {"a": SocketType.BIT, "b": SocketType.BIT}
DEMO_OUTPUTS = {"o": SocketType.BIT}
DEMO_NODE_COUNT = 3


class MainWindow(QMainWindow):
    """Main Window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Amaranth Companion")

        self._open_modules: list[Module] = []
        self._scene_view: ModuleSceneView | None = None

        self._create_actions()
        self._create_menu_bar()
        self._create_tool_bars()
        self._create_status_bar()

    # --- construction ------------------------------------------------------

    def _create_actions(self) -> None:
        for spec in ACTIONS:
            action = QAction(spec.text, self)
            if spec.icon:
                action.setIcon(QIcon(spec.icon))
            if spec.shortcuts:
                action.setShortcuts([QKeySequence(s) for s in spec.shortcuts])
            if spec.tip:
                action.setStatusTip(spec.tip)
                action.setToolTip(spec.tip)
            action.triggered.connect(getattr(self, spec.slot))
            setattr(self, self._action_attr(spec.name), action)

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
                elif isinstance(entry, SubmenuSpec):
                    self._add_placeholder_submenu(menu, entry)
                else:
                    menu.addAction(self._action(entry))

        self.setMenuBar(menu_bar)

    @staticmethod
    def _add_placeholder_submenu(parent: QMenu, spec: SubmenuSpec) -> None:
        submenu = parent.addMenu(spec.title)
        for text in spec.placeholders:
            submenu.addAction(text).setEnabled(False)

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

    # --- open modules ------------------------------------------------------

    @property
    def current_module(self) -> Module | None:
        return self._open_modules[-1] if self._open_modules else None

    @property
    def current_view(self) -> ModuleSceneView | None:
        return self._scene_view

    def open_module(self, module: Module) -> None:
        self._open_modules.append(module)

        if self._scene_view is None:
            self._scene_view = ModuleSceneView()
            self.setCentralWidget(self._scene_view)

        self._scene_view.module = module

    def close_module(self, module: Module) -> None:
        self._open_modules.remove(module)

        if self.current_module is not None:
            self._scene_view.module = self.current_module
            return

        self._scene_view.setScene(None)
        # QMainWindow takes ownership, so the old view is destroyed here
        self.setCentralWidget(None)
        self._scene_view = None

    # --- file actions ------------------------------------------------------

    def new_file(self) -> None:
        module = Module()

        nodes: list[Node] = []
        for index in range(DEMO_NODE_COUNT):
            node = Node(module, NodeContentWidget(), DEMO_INPUTS, DEMO_OUTPUTS)
            module.add_node(node)
            node.pos = (-300 + index * 300, -300 + index * 100)
            nodes.append(node)

        module.add_edge(Edge(nodes[0].output_sockets["o"], nodes[1].input_sockets["a"]))

        # the placeholder content is the baseline, not an undoable step
        module.history.reset()
        self.open_module(module)

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open graph from file", "", FILE_FILTER
        )
        if not path:
            return

        try:
            module = Module.from_file(path)
        except (OSError, ValueError, KeyError) as error:
            self._report(f"Could not open {path}", error)
            return

        self.open_module(module)
        self.statusbar.showMessage(f"Opened {path}", 5000)

    def save_file(self) -> None:
        module = self.current_module
        if module is None:
            return

        if module.path is None:
            self.save_as_file()
        else:
            self._save(module, module.path)

    def save_as_file(self) -> None:
        module = self.current_module
        if module is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save graph to file", "", FILE_FILTER
        )
        if path:
            self._save(module, path)

    def _save(self, module: Module, path: str) -> None:
        try:
            module.save(path)
        except OSError as error:
            self._report(f"Could not save to {path}", error)
            return

        self.statusbar.showMessage(f"Saved as {path}", 5000)

    def close_file(self) -> None:
        if self.current_module is not None:
            self.close_module(self.current_module)

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

    def undo(self) -> None:
        if self.current_module is not None:
            self.current_module.history.undo()

    def redo(self) -> None:
        if self.current_module is not None:
            self.current_module.history.redo()

    # --- view actions ------------------------------------------------------

    def zoom_in(self) -> None:
        if self.current_view is not None:
            self.current_view.zoom_in_out(1)

    def zoom_out(self) -> None:
        if self.current_view is not None:
            self.current_view.zoom_in_out(-1)

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

    def _report(self, message: str, error: Exception) -> None:
        log.warning("%s: %s", message, error)
        self.statusbar.showMessage(message, 5000)
