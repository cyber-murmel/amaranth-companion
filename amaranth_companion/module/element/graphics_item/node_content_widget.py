from PyQt5.QtWidgets import *


class NodeContentWidget(QWidget):
    def __init__(self, parent=None, text=""):
        super().__init__(parent)

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        self.wdg_label = QLabel("Some Title")
        self.layout.addWidget(self.wdg_label)
        self.text_edit = QTextEdit()
        self.text_edit.insertPlainText(text)
        self.layout.addWidget(self.text_edit)
