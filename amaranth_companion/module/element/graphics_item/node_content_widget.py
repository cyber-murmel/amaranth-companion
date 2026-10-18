from PyQt5.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget


class NodeContentWidget(QWidget):
    def __init__(self, parent=None, text: str = ""):
        super().__init__(parent)

        # not `self.layout`: that would shadow QWidget.layout()
        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._layout)

        self.label = QLabel("Some Title")
        self._layout.addWidget(self.label)

        self.text_edit = QTextEdit()
        self.text_edit.insertPlainText(text)
        self._layout.addWidget(self.text_edit)

    @property
    def text(self) -> str:
        return self.text_edit.toPlainText()

    @text.setter
    def text(self, value: str) -> None:
        self.text_edit.setPlainText(value)
