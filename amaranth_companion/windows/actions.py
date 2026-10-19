"""Declarative description of the main window's actions, menus and toolbars.

Keeping these as data rather than ~130 lines of repetitive ``QAction``
construction means an action cannot be created, bound and connected but then
left out of every menu -- which is what happened to "Save As".

Shortcuts are spelled out rather than using ``QKeySequence.StandardKey``:
several standard keys (``SaveAs``, ``Quit``) resolve to *no* binding at all on
this platform, so ``setShortcut(QKeySequence.SaveAs)`` silently bound nothing.
"""

from dataclasses import dataclass, field

from ..theme import ThemeMode


@dataclass(frozen=True)
class ActionSpec:
    """One ``QAction``. ``name`` is the window attribute, ``slot`` its method."""

    name: str
    text: str
    slot: str
    icon: str | None = None
    shortcuts: tuple[str, ...] = ()
    tip: str | None = None
    #: draw as a radio/check entry rather than a plain command
    checkable: bool = False
    #: name of the exclusive group this action belongs to, if any
    group: str | None = None


@dataclass(frozen=True)
class SubmenuSpec:
    """A submenu.

    ``entries`` are action names, spelled exactly as in :data:`ACTIONS`.
    ``placeholders`` are labels for behaviour the application does not have
    yet; they are added disabled, so the menu does not advertise it.
    """

    title: str
    placeholders: tuple[str, ...] = field(default_factory=tuple)
    entries: tuple[str, ...] = field(default_factory=tuple)


#: marker for a separator line in a menu layout
SEPARATOR = object()

#: marker for the Insert menu. Its entries are generated from the block
#: library at build time rather than listed here, so dropping a definition
#: into the blocks directory is enough to make it insertable.
INSERT_MENU = object()

#: marker for the Open Example submenu, filled from the shipped index
EXAMPLES_MENU = object()

#: marker for the Board submenu, filled from the platforms installed here
BOARDS_MENU = object()

#: marker for the Panels submenu, filled from the docks' own toggle actions
PANELS_MENU = object()

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
    ActionSpec(
        "export",
        "&Export Amaranth...",
        "export_design",
        shortcuts=("Ctrl+E",),
        tip="Write the design out as an amaranth package",
    ),
    ActionSpec("exit", "&Exit", "close", shortcuts=("Ctrl+Q",)),
    # edit
    ActionSpec("copy", "&Copy", "copy_content", ":copy.svg", ("Ctrl+C",)),
    ActionSpec("paste", "&Paste", "paste_content", ":paste.svg", ("Ctrl+V",)),
    ActionSpec("cut", "C&ut", "cut_content", ":cut.svg", ("Ctrl+X",)),
    ActionSpec(
        "create_block",
        "Create &Block from Module...",
        "create_block_from_module",
        shortcuts=("Ctrl+Shift+B",),
        tip="Save what is on this canvas as a reusable block",
    ),
    ActionSpec(
        "rename",
        "Re&name Block",
        "rename_node",
        shortcuts=("F2",),
        tip="Rename the selected block",
    ),
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
    ActionSpec(
        "go_up",
        "Go &Up",
        "go_up",
        shortcuts=("Escape", "Alt+Up"),
        tip="Leave this block and return to the level above",
    ),
    ActionSpec(
        "refresh_ports",
        "&Refresh Ports",
        "refresh_ports",
        shortcuts=("F5",),
        tip="Re-read the ports of the selected blocks from their code",
    ),
    ActionSpec(
        "run_tests",
        "&Run Tests",
        "run_tests",
        ":test.svg",
        ("F6",),
        "Run every testbench and formal block in the design",
    ),
    ActionSpec(
        "simulate",
        "&Simulate...",
        "simulate_design",
        ":wave.svg",
        ("F7",),
        "Run the design for a while and open the waveform viewer",
    ),
    ActionSpec(
        "build",
        "&Build Bitstream",
        "build_design",
        ":run.svg",
        ("F8",),
        "Synthesise the design for the chosen board",
    ),
    ActionSpec(
        "program",
        "Build and &Program",
        "program_design",
        shortcuts=("Shift+F8",),
        tip="Build the design and load it onto an attached board",
    ),
    # the text comes from ThemeMode so the menu and the --theme values cannot
    # drift apart
    ActionSpec(
        "theme_auto",
        ThemeMode.AUTO.title,
        "use_theme_auto",
        tip="Match the desktop's light or dark preference",
        checkable=True,
        group="theme",
    ),
    ActionSpec(
        "theme_light",
        ThemeMode.LIGHT.title,
        "use_theme_light",
        tip="Always use the light theme",
        checkable=True,
        group="theme",
    ),
    ActionSpec(
        "theme_dark",
        ThemeMode.DARK.title,
        "use_theme_dark",
        tip="Always use the dark theme",
        checkable=True,
        group="theme",
    ),
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
            EXAMPLES_MENU,
            "save",
            "save_as",
            "close",
            SEPARATOR,
            "export",
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
            "rename",
            SEPARATOR,
            "undo",
            "redo",
            SEPARATOR,
            SubmenuSpec("Find and Replace", ("Find...", "Replace...")),
        ),
    ),
    ("&Insert", (INSERT_MENU, SEPARATOR, "create_block")),
    (
        "&View",
        (
            "zoom_in",
            "zoom_out",
            SEPARATOR,
            "go_up",
            "refresh_ports",
            "run_tests",
            "simulate",
            SEPARATOR,
            SubmenuSpec("&Theme", entries=("theme_auto", "theme_light", "theme_dark")),
            PANELS_MENU,
        ),
    ),
    (
        "&Build",
        (
            BOARDS_MENU,
            SEPARATOR,
            "build",
            "program",
        ),
    ),
    ("&Help", ("help_content", "about")),
)

TOOLBARS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("File", ("new", "open", "save")),
    ("Edit", ("copy", "paste", "cut")),
    ("View", ("zoom_in", "zoom_out", "go_up")),
    ("Run", ("run_tests", "simulate", "build")),
)

#: menu action name for each theme mode, used to sync the checked entry
THEME_ACTIONS: dict[ThemeMode, str] = {
    ThemeMode.AUTO: "theme_auto",
    ThemeMode.LIGHT: "theme_light",
    ThemeMode.DARK: "theme_dark",
}
