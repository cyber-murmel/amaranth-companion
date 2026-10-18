"""Declarative description of the main window's actions, menus and toolbars.

Keeping these as data rather than ~130 lines of repetitive ``QAction``
construction means an action cannot be created, bound and connected but then
left out of every menu -- which is what happened to "Save As".

Shortcuts are spelled out rather than using ``QKeySequence.StandardKey``:
several standard keys (``SaveAs``, ``Quit``) resolve to *no* binding at all on
this platform, so ``setShortcut(QKeySequence.SaveAs)`` silently bound nothing.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ActionSpec:
    """One ``QAction``. ``name`` is the window attribute, ``slot`` its method."""

    name: str
    text: str
    slot: str
    icon: str | None = None
    shortcuts: tuple[str, ...] = ()
    tip: str | None = None


@dataclass(frozen=True)
class SubmenuSpec:
    """A submenu whose entries are not implemented yet.

    The entries are added disabled, so the menu does not advertise behaviour
    the application does not have.
    """

    title: str
    placeholders: tuple[str, ...] = field(default_factory=tuple)


#: marker for a separator line in a menu layout
SEPARATOR = object()

ACTIONS: tuple[ActionSpec, ...] = (
    # file
    ActionSpec(
        "new", "&New", "new_file", ":new.svg", ("Ctrl+N",), "Create a new module"
    ),
    ActionSpec(
        "open", "&Open...", "open_file", ":open.svg", ("Ctrl+O",), "Open a module"
    ),
    ActionSpec(
        "save", "&Save", "save_file", ":save.svg", ("Ctrl+S",), "Save the module"
    ),
    ActionSpec(
        "save_as",
        "Save &As...",
        "save_as_file",
        shortcuts=("Ctrl+Shift+S",),
        tip="Save the module under a new name",
    ),
    ActionSpec("close", "&Close", "close_file", shortcuts=("Ctrl+W",)),
    ActionSpec("exit", "&Exit", "close", shortcuts=("Ctrl+Q",)),
    # edit
    ActionSpec("copy", "&Copy", "copy_content", ":copy.svg", ("Ctrl+C",)),
    ActionSpec("paste", "&Paste", "paste_content", ":paste.svg", ("Ctrl+V",)),
    ActionSpec("cut", "C&ut", "cut_content", ":cut.svg", ("Ctrl+X",)),
    ActionSpec("undo", "U&ndo", "undo", shortcuts=("Ctrl+Z",)),
    ActionSpec("redo", "&Redo", "redo", shortcuts=("Ctrl+Shift+Z", "Ctrl+Y")),
    # view
    ActionSpec(
        "zoom_in",
        "Zoom &In",
        "zoom_in",
        ":zoom-in.svg",
        # both, rather than one setShortcut call overwriting the other
        ("Ctrl++", "Ctrl+="),
    ),
    ActionSpec("zoom_out", "Zoom &Out", "zoom_out", ":zoom-out.svg", ("Ctrl+-",)),
    # help
    ActionSpec("help_content", "&Help Content", "help_content"),
    ActionSpec("about", "&About", "about"),
)

MENUS: tuple[tuple[str, tuple], ...] = (
    (
        "&File",
        (
            "new",
            "open",
            # TODO: back this with a real recent-files list
            SubmenuSpec("Open Recent", ("No recent files",)),
            "save",
            "save_as",
            "close",
            SEPARATOR,
            "exit",
        ),
    ),
    (
        "&Edit",
        (
            "copy",
            "paste",
            "cut",
            SEPARATOR,
            "undo",
            "redo",
            SEPARATOR,
            SubmenuSpec("Find and Replace", ("Find...", "Replace...")),
        ),
    ),
    ("&View", ("zoom_in", "zoom_out")),
    ("&Help", ("help_content", "about")),
)

TOOLBARS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("File", ("new", "open", "save")),
    ("Edit", ("copy", "paste", "cut")),
    ("View", ("zoom_in", "zoom_out")),
)
