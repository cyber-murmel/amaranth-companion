from functools import partial

from PyQt5.QtWidgets import (
    QLabel,
    QMainWindow,
    QMenuBar,
    QMenu,
    QToolBar,
    QAction,
    QScrollArea,
    QGroupBox,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QIcon, QKeySequence


class DraggableLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.pos()
            self._pos = self.pos()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            delta = event.pos() - self.drag_start_position
            self._pos += delta
            # self.move(self._pos)
            self.move(
                int((self.x() + delta.x()) / 32) * 32,
                int((self.y() + delta.y()) / 32) * 32,
            )


class MainWindow(QMainWindow):
    """Main Window."""

    def __init__(self, parent=None):
        """Initializer."""
        super().__init__(parent)
        self.setWindowTitle("Amaranth Companion")

        self.scroll = QScrollArea()
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setCentralWidget(self.scroll)

        self.widget = QWidget()
        self.widget.setGeometry(0, 0, 2000, 1000)
        self.scroll.setWidget(self.widget)

        self.layout = QVBoxLayout()
        self.widget.setLayout(self.layout)

        self.centralLabel = QLabel("Hello, World")
        self.centralLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.layout.addWidget(self.centralLabel)

        self._createActions()
        self._createMenuBar()
        self._createToolBars()
        self._createStatusBar()
        self._createContextMenu()
        self._connectActions()

        label = DraggableLabel(self.widget)
        label.setText("Drag me!")
        label.setGeometry(50, 50, 100, 30)

    # def wheelEvent(self, event):
    #     print(event.angleDelta())

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
        # Setting contextMenuPolicy
        self.centralLabel.setContextMenuPolicy(Qt.ActionsContextMenu)

        # Populating the widget with action
        self.centralLabel.addAction(self.newAction)
        self.centralLabel.addAction(self.openAction)
        self.centralLabel.addAction(self.saveAction)

        separator = QAction(self)
        separator.setSeparator(True)
        self.centralLabel.addAction(separator)

        self.centralLabel.addAction(self.copyAction)
        self.centralLabel.addAction(self.pasteAction)
        self.centralLabel.addAction(self.cutAction)

    def newFile(self):
        # Logic for creating a new file goes here...
        self.centralLabel.setText("<b>File > New</b> clicked")

    def openFile(self):
        # Logic for opening an existing file goes here...
        self.centralLabel.setText("<b>File > Open...</b> clicked")

    def openRecentFile(self, filename):
        # Logic for opening a recent file goes here...
        self.centralLabel.setText(f"<b>{filename}</b> opened")

    def saveFile(self):
        # Logic for saving a file goes here...
        self.centralLabel.setText("<b>File > Save</b> clicked")

    def copyContent(self):
        # Logic for copying content goes here...
        self.centralLabel.setText("<b>Edit > Copy</b> clicked")

    def pasteContent(self):
        # Logic for pasting content goes here...
        self.centralLabel.setText("<b>Edit > Paste</b> clicked")

    def cutContent(self):
        # Logic for cutting content goes here...
        self.centralLabel.setText("<b>Edit > Cut</b> clicked")

    def zoomIn(self):
        self.centralLabel.setText("<b>Zoom In</b> clicked")

    def zoomOut(self):
        self.centralLabel.setText("<b>Zoom Out</b> clicked")

    def helpContent(self):
        # Logic for launching help goes here...
        self.centralLabel.setText("<b>Help > Help Content...</b> clicked")

    def about(self):
        # Logic for showing an about dialog content goes here...
        self.centralLabel.setText("<b>Help > About...</b> clicked")

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
