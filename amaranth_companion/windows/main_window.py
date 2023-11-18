from functools import partial

from PyQt5.QtWidgets import (
    QMainWindow,
    QMenuBar,
    QMenu,
    QToolBar,
    QAction,
    QGraphicsItem,
)
from PyQt5.QtGui import QIcon, QKeySequence

from ..module import Module, ModuleSceneView
from ..node import Node, NodeContentWidget
from ..edge import Edge


class MainWindow(QMainWindow):
    """Main Window."""

    def __init__(self, parent=None):
        """Initializer."""
        super().__init__(parent)
        self.setWindowTitle("Amaranth Companion")

        self._createActions()
        self._createMenuBar()
        self._createToolBars()
        self._createStatusBar()
        self._createContextMenu()
        self._connectActions()

        self.scene_view = ModuleSceneView(parent=self)

        self.setCentralWidget(self.scene_view)

    def openModule(self, module):
        self.scene_view.scene = module.scene

    def _createMenuBar(self):
        menuBar = QMenuBar(self)
        # File menu
        ## Creating menus using a QMenu object
        fileMenu = QMenu("&File", self)
        menuBar.addMenu(fileMenu)  #
        fileMenu.addAction(self.newAction)
        fileMenu.addAction(self.openAction)
        self.openRecentMenu = fileMenu.addMenu("Open Recent")
        fileMenu.addAction(self.saveAction)
        fileMenu.addSeparator()
        fileMenu.addAction(self.exitAction)

        # Edit menu
        ## Creating menus using a title
        editMenu = menuBar.addMenu("&Edit")
        editMenu.addAction(self.copyAction)
        editMenu.addAction(self.pasteAction)
        editMenu.addAction(self.cutAction)

        editMenu.addSeparator()
        ## Find and Replace submenu in the Edit menu
        findMenu = editMenu.addMenu("Find and Replace")
        findMenu.addAction("Find...")
        findMenu.addAction("Replace...")

        # Help menu
        viewMenu = menuBar.addMenu("&View")
        viewMenu.addAction(self.zoomInAction)
        viewMenu.addAction(self.zoomOutAction)

        # Help menu
        helpMenu = menuBar.addMenu("&Help")
        helpMenu.addAction(self.helpContentAction)
        helpMenu.addAction(self.aboutAction)

        self.setMenuBar(menuBar)

    def _createToolBars(self):
        # Using a title
        fileToolBar = self.addToolBar("File")
        fileToolBar.addAction(self.newAction)
        fileToolBar.addAction(self.openAction)
        fileToolBar.addAction(self.saveAction)
        fileToolBar.setMovable(False)
        # Using a QToolBar object
        editToolBar = QToolBar("Edit", self)
        self.addToolBar(editToolBar)
        editToolBar.addAction(self.copyAction)
        editToolBar.addAction(self.pasteAction)
        editToolBar.addAction(self.cutAction)
        # Using a QToolBar object
        viewToolBar = QToolBar("View", self)
        self.addToolBar(viewToolBar)
        viewToolBar.addAction(self.zoomInAction)
        viewToolBar.addAction(self.zoomOutAction)
        # # Using a QToolBar object and a toolbar area
        # helpToolBar = QToolBar("Help", self)
        # self.addToolBar(Qt.LeftToolBarArea, helpToolBar)

    def _createStatusBar(self):
        self.statusbar = self.statusBar()
        # Adding a temporary message
        self.statusbar.showMessage("Ready", 3000)

    def _createActions(self):
        # File actions
        ## Creating action using the first constructor
        self.newAction = QAction(self)
        self.newAction.setText("&New")
        self.newAction.setIcon(QIcon(":new.svg"))
        ## Creating actions using the second constructor
        self.openAction = QAction(QIcon(":open.svg"), "&Open...", self)
        self.saveAction = QAction(QIcon(":save.svg"), "&Save", self)
        self.exitAction = QAction("&Exit", self)
        ## Using string-based key sequences
        self.newAction.setShortcut("Ctrl+N")
        self.openAction.setShortcut("Ctrl+O")
        self.saveAction.setShortcut("Ctrl+S")
        self.exitAction.setShortcut("Ctrl+Q")
        # Edit actions
        self.copyAction = QAction(QIcon(":copy.svg"), "&Copy", self)
        self.pasteAction = QAction(QIcon(":paste.svg"), "&Paste", self)
        self.cutAction = QAction(QIcon(":cut.svg"), "C&ut", self)
        ## Using standard keys
        self.copyAction.setShortcut(QKeySequence.Copy)
        self.pasteAction.setShortcut(QKeySequence.Paste)
        self.cutAction.setShortcut(QKeySequence.Cut)
        # view actions
        self.zoomInAction = QAction(QIcon(":zoom-in.svg"), "Zoom &In", self)
        self.zoomOutAction = QAction(QIcon(":zoom-out.svg"), "Zoom &Out", self)
        self.zoomInAction.setShortcut("Ctrl++")
        self.zoomInAction.setShortcut("Ctrl+=")
        self.zoomOutAction.setShortcut("Ctrl+-")
        ## Using standard keys
        self.copyAction.setShortcut(QKeySequence.Copy)
        self.pasteAction.setShortcut(QKeySequence.Paste)
        self.cutAction.setShortcut(QKeySequence.Cut)
        # Help actions
        self.helpContentAction = QAction("&Help Content", self)
        self.aboutAction = QAction("&About", self)

    def _connectActions(self):
        # Connect File actions
        self.newAction.triggered.connect(self.newFile)
        newTip = "Create a new file"
        self.newAction.setStatusTip(newTip)
        self.newAction.setToolTip(newTip)
        self.openAction.triggered.connect(self.openFile)
        self.saveAction.triggered.connect(self.saveFile)
        self.exitAction.triggered.connect(self.close)
        # Connect Edit actions
        self.copyAction.triggered.connect(self.copyContent)
        self.pasteAction.triggered.connect(self.pasteContent)
        self.cutAction.triggered.connect(self.cutContent)
        # Connect Edit actions
        self.zoomInAction.triggered.connect(self.zoomIn)
        self.zoomOutAction.triggered.connect(self.zoomOut)
        # Connect Help actions
        self.helpContentAction.triggered.connect(self.helpContent)
        self.aboutAction.triggered.connect(self.about)
        # Connect Open Recent to dynamically populate it
        self.openRecentMenu.aboutToShow.connect(self.populateOpenRecent)

    def _createContextMenu(self):
        pass

    def newFile(self):
        self.module = Module()
        # self.module.scene.addDebugContent()
        nodes: [Node] = []
        for i in range(3):
            node = Node(f"{i}", NodeContentWidget(), [1, 1, 1], [1, 1])
            self.module.addNode(node)
            node.pos = (50 + i * 250, 50 + i * 50)
            nodes.append(node)
            # print(node.pos)

        edge = Edge(nodes[0]._outputs[0], nodes[1]._inputs[0])

        self.module.addEdge(edge)

        self.openModule(self.module)

    def openFile(self):
        pass

    def openRecentFile(self, filename):
        pass

    def saveFile(self):
        pass

    def copyContent(self):
        pass

    def pasteContent(self):
        pass

    def cutContent(self):
        pass

    def zoomIn(self):
        self.scene_view.zoomInOut(1)

    def zoomOut(self):
        self.scene_view.zoomInOut(-1)

    def helpContent(self):
        pass

    def about(self):
        pass

    def populateOpenRecent(self):
        # Step 1. Remove the old options from the menu
        self.openRecentMenu.clear()
        # Step 2. Dynamically create the actions
        actions = []
        filenames = [f"File-{n}" for n in range(5)]
        for filename in filenames:
            action = QAction(filename, self)
            action.triggered.connect(partial(self.openRecentFile, filename))
            actions.append(action)
        # Step 3. Add the actions to the menu
        self.openRecentMenu.addActions(actions)
