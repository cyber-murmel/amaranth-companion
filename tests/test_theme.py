from PyQt5.QtGui import QPalette

import pytest

from amaranth_companion import theme as theme_module
from amaranth_companion.theme import (
    DARK_THEME,
    LIGHT_THEME,
    ThemeMode,
    current_theme,
    resolve,
    theme_manager,
)
from amaranth_companion.windows.actions import THEME_ACTIONS


@pytest.fixture(autouse=True)
def restore_theme(qapp):
    """Leave the process on the theme it started with."""
    manager = theme_manager()
    mode = manager.mode
    yield
    manager.apply(mode, persist=False)


def test_explicit_modes_resolve_to_their_theme():
    assert resolve(ThemeMode.LIGHT) is LIGHT_THEME
    assert resolve(ThemeMode.DARK) is DARK_THEME


def test_auto_resolves_to_one_of_the_themes():
    assert resolve(ThemeMode.AUTO) in (LIGHT_THEME, DARK_THEME)


def test_detect_falls_back_to_light_without_any_signal(monkeypatch):
    monkeypatch.setattr(theme_module, "_gnome_color_scheme", lambda: None)
    monkeypatch.setattr(theme_module, "_system_palette", None)
    assert theme_module.detect_system_mode() is ThemeMode.LIGHT


def test_detect_follows_a_dark_platform_palette(monkeypatch):
    monkeypatch.setattr(theme_module, "_gnome_color_scheme", lambda: None)
    palette = QPalette()
    palette.setColor(QPalette.Window, DARK_THEME.window)
    monkeypatch.setattr(theme_module, "_system_palette", palette)
    assert theme_module.detect_system_mode() is ThemeMode.DARK


def test_desktop_preference_wins_over_the_palette(monkeypatch):
    monkeypatch.setattr(theme_module, "_gnome_color_scheme", lambda: ThemeMode.LIGHT)
    palette = QPalette()
    palette.setColor(QPalette.Window, DARK_THEME.window)
    monkeypatch.setattr(theme_module, "_system_palette", palette)
    assert theme_module.detect_system_mode() is ThemeMode.LIGHT


def test_apply_swaps_the_application_palette(qapp):
    theme_manager().apply(ThemeMode.DARK, persist=False)
    assert current_theme() is DARK_THEME
    assert qapp.palette().color(QPalette.Window) == DARK_THEME.window

    theme_manager().apply(ThemeMode.LIGHT, persist=False)
    assert current_theme() is LIGHT_THEME
    assert qapp.palette().color(QPalette.Window) == LIGHT_THEME.window


def test_switching_repaints_existing_nodes(chain):
    _, nodes = chain
    title_item = nodes[0].graphics_item._title_item

    theme_manager().apply(ThemeMode.DARK, persist=False)
    assert title_item.defaultTextColor() == DARK_THEME.node_title_text

    theme_manager().apply(ThemeMode.LIGHT, persist=False)
    assert title_item.defaultTextColor() == LIGHT_THEME.node_title_text


def test_every_mode_has_a_menu_title():
    assert len({mode.title for mode in ThemeMode}) == len(ThemeMode)


# --- menu integration -------------------------------------------------------


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    """A main window whose theme preference is written to a throwaway file."""
    from PyQt5.QtCore import QSettings

    from amaranth_companion.windows.main_window import MainWindow

    monkeypatch.setattr(
        theme_module.ThemeManager,
        "settings",
        staticmethod(
            lambda: QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
        ),
    )
    return MainWindow()


def test_theme_menu_entries_are_mutually_exclusive(window):
    actions = [window._action(name) for name in THEME_ACTIONS.values()]
    assert all(action.isCheckable() for action in actions)
    assert sum(action.isChecked() for action in actions) == 1


def test_theme_menu_follows_the_active_mode(window):
    window.set_theme(ThemeMode.DARK)
    assert current_theme() is DARK_THEME
    assert window.theme_dark_action.isChecked()
    assert not window.theme_light_action.isChecked()

    window.set_theme(ThemeMode.LIGHT)
    assert window.theme_light_action.isChecked()
    assert not window.theme_dark_action.isChecked()


def test_theme_choice_is_remembered(window):
    window.set_theme(ThemeMode.DARK)
    assert theme_module.ThemeManager.stored_mode() is ThemeMode.DARK


def test_window_opens_big_enough_to_work_in(window):
    from amaranth_companion.windows.main_window import MINIMUM_SIZE

    assert window.width() >= MINIMUM_SIZE[0]
    assert window.height() >= MINIMUM_SIZE[1]


# --- the command line -------------------------------------------------------


def test_the_theme_can_be_chosen_on_the_command_line():
    from amaranth_companion.__main__ import parse_arguments

    assert parse_arguments(["--theme", "dark"]).theme == "dark"
    assert parse_arguments([]).theme is None


def test_an_unknown_theme_is_refused():
    from amaranth_companion.__main__ import parse_arguments

    with pytest.raises(SystemExit):
        parse_arguments(["--theme", "neon"])


def test_a_command_line_theme_does_not_overwrite_the_stored_one(qapp, tmp_path):
    """`--theme dark` is for this run, not a silent preference change."""
    from PyQt5.QtCore import QSettings

    settings = QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat)
    manager = theme_manager()
    mode = manager.mode

    try:
        theme_module.ThemeManager.settings = staticmethod(lambda: settings)
        settings.setValue(theme_module.SETTINGS_KEY_THEME, ThemeMode.LIGHT.value)

        theme_module.install(ThemeMode.DARK)

        assert current_theme() is DARK_THEME
        assert theme_module.ThemeManager.stored_mode() is ThemeMode.LIGHT
    finally:
        del theme_module.ThemeManager.settings
        manager.apply(mode, persist=False)


@pytest.mark.parametrize(
    "verbose, quiet, expected",
    [
        (0, False, "WARNING"),
        (1, False, "INFO"),
        (2, False, "DEBUG"),
        (0, True, "ERROR"),
    ],
)
def test_verbosity_maps_to_a_log_level(verbose, quiet, expected):
    import logging

    from amaranth_companion.__main__ import get_log_level

    assert get_log_level(verbose, quiet) == getattr(logging, expected)


def test_verbose_and_quiet_are_mutually_exclusive():
    from amaranth_companion.__main__ import parse_arguments

    with pytest.raises(SystemExit):
        parse_arguments(["-v", "-q"])
