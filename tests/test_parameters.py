"""Variable blocks, parameter wiring, socket labels and block icons."""

import pytest

from amaranth_companion.blocks.definition import BlockDefinition, BlockKind, Shape
from amaranth_companion.blocks.library import library
from amaranth_companion.design import Design
from amaranth_companion.module.element import Edge
from amaranth_companion.module.instantiate import instantiate, refresh_node_ports
from amaranth_companion.module.parameters import (
    ParameterError,
    evaluate,
    module_variables,
    resolve_params,
    split_assignment,
)
from amaranth_companion.theme import DARK_THEME, LIGHT_THEME, ThemeMode, theme_manager

WIDTH_BLOCK = """
from amaranth import *


class Bus(Elaboratable):
    def __init__(self, width_param=1):
        self.data_in = Signal(width_param)
        self.data_out = Signal(width_param)

    def elaborate(self, platform):
        return Module()
"""


@pytest.fixture
def design(qapp):
    return Design()


def variable(module, text, pos=(0, 0)):
    return instantiate(
        module, library().require("builtin.variable"), text=text, pos=pos
    )


def code(module, source=WIDTH_BLOCK, pos=(0, 0)):
    return instantiate(module, library().require("builtin.code"), text=source, pos=pos)


# --- evaluating -------------------------------------------------------------


@pytest.mark.parametrize(
    "expression, expected",
    [("8", 8), ("'x'", "x"), ("(1, 2)", (1, 2)), ("True", True), ("-3", -3)],
)
def test_literals_evaluate(expression, expected):
    assert evaluate(expression) == expected


def test_arithmetic_evaluates():
    assert evaluate("int(100 / 4) + max(1, 2)") == 27


def test_other_variables_are_in_scope():
    assert evaluate("period // 2", {"period": 100}) == 50


def test_an_empty_expression_is_an_error():
    with pytest.raises(ParameterError):
        evaluate("   ")


def test_an_unknown_name_is_an_error():
    with pytest.raises(ParameterError):
        evaluate("nonexistent + 1")


def test_the_evaluator_has_no_import():
    """A typo in a bit width must not be able to reach the filesystem."""
    with pytest.raises(ParameterError):
        evaluate("__import__('os').getcwd()")


def test_the_evaluator_has_no_open():
    with pytest.raises(ParameterError):
        evaluate("open('/etc/passwd').read()")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("width = 8", ("width", "8")),
        ("  half  =  period // 2 ", ("half", "period // 2")),
        ("8", ("", "8")),
    ],
)
def test_assignments_split(text, expected):
    assert split_assignment(text) == expected


# --- variable blocks --------------------------------------------------------


def test_a_variable_exposes_a_parameter_output(design):
    node = variable(design.current_module, "width = 8")

    assert list(node.output_sockets) == ["width_param"]
    assert node.output_sockets["width_param"].is_param


def test_renaming_a_variable_renames_its_port(design):
    node = variable(design.current_module, "width = 8")

    node.text = "depth = 4"
    refresh_node_ports(node)

    assert list(node.output_sockets) == ["depth_param"]


def test_variables_resolve_against_each_other(design):
    module = design.current_module
    variable(module, "period = 100")
    variable(module, "half = period // 2", pos=(0, 150))

    assert module_variables(module) == {"period": 100, "half": 50}


def test_declaration_order_does_not_matter(design):
    """A variable may refer to one defined below or to the right of it."""
    module = design.current_module
    variable(module, "half = period // 2")
    variable(module, "period = 100", pos=(0, 150))

    assert module_variables(module)["half"] == 50


def test_a_cycle_is_dropped_rather_than_looped_on(design):
    module = design.current_module
    variable(module, "x = y + 1")
    variable(module, "y = x + 1", pos=(0, 150))
    variable(module, "ok = 3", pos=(0, 300))

    values = module_variables(module)

    assert values == {"ok": 3}


# --- parameter wiring -------------------------------------------------------


def test_an_unconnected_parameter_uses_its_default(design):
    node = code(design.current_module)

    assert node.input_sockets["data_in"].shape == Shape(1, False)


def test_a_wired_variable_resizes_the_ports(design):
    module = design.current_module
    var = variable(module, "width = 8", pos=(-400, 0))
    node = code(module)

    module.add_edge(
        Edge(var.output_sockets["width_param"], node.input_sockets["width_param"])
    )
    refresh_node_ports(node)

    assert node.input_sockets["data_in"].shape == Shape(8, False)
    assert node.output_sockets["data_out"].shape == Shape(8, False)


def test_changing_the_variable_resizes_again(design):
    module = design.current_module
    var = variable(module, "width = 8", pos=(-400, 0))
    node = code(module)
    module.add_edge(
        Edge(var.output_sockets["width_param"], node.input_sockets["width_param"])
    )
    refresh_node_ports(node)

    var.text = "width = 24"
    diff, _error = refresh_node_ports(node)

    assert sorted(diff.reshaped) == ["data_in", "data_out"]
    assert node.input_sockets["data_in"].shape == Shape(24, False)


def test_resizing_keeps_the_signal_edges(design):
    """A width change must not cost the user their wiring."""
    module = design.current_module
    var = variable(module, "width = 8", pos=(-400, 0))
    upstream = code(module, pos=(-400, 300))
    node = code(module)
    module.add_edge(
        Edge(upstream.output_sockets["data_out"], node.input_sockets["data_in"])
    )
    module.add_edge(
        Edge(var.output_sockets["width_param"], node.input_sockets["width_param"])
    )

    diff, _error = refresh_node_ports(node)

    assert diff.dropped_edges == 0
    assert len(node.input_sockets["data_in"].edges) == 1


def test_a_broken_variable_is_reported_on_the_consumer(design):
    module = design.current_module
    var = variable(module, "width = nonsense", pos=(-400, 0))
    node = code(module)
    module.add_edge(
        Edge(var.output_sockets["width_param"], node.input_sockets["width_param"])
    )

    _diff, error = refresh_node_ports(node)

    assert "width" in error


def test_resolve_params_reports_values(design):
    module = design.current_module
    var = variable(module, "width = 5", pos=(-400, 0))
    node = code(module)
    module.add_edge(
        Edge(var.output_sockets["width_param"], node.input_sockets["width_param"])
    )

    values, error = resolve_params(node)

    assert values["width_param"] == 5
    assert error == ""


def test_a_parameter_crosses_into_an_implementation(design):
    """A ``*_param`` port block inside reads the value the block was given."""
    gate = design.instantiate(library().require("logic.and2"))
    child = gate.child_module
    gate.set_param("width_param", 6)

    port = instantiate(
        child, library().require("builtin.port_param"), text="width", pos=(-700, 300)
    )
    inner = code(child, pos=(-100, 400))
    child.add_edge(
        Edge(port.output_sockets["width_param"], inner.input_sockets["width_param"])
    )
    refresh_node_ports(inner)

    assert inner.input_sockets["data_in"].shape == Shape(6, False)


# --- socket labels ----------------------------------------------------------


def test_a_socket_label_drops_the_role_suffix(design):
    """The side and the shape already say the role; repeating it is noise."""
    node = code(design.current_module)

    assert node.input_sockets["data_in"].label == "data"
    assert node.output_sockets["data_out"].label == "data"
    assert node.input_sockets["width_param"].label == "width"


def test_the_label_is_drawn_inside_the_socket_gutter(design):
    """Labels must not land under the content widget."""
    from amaranth_companion.module.element.graphics_item.node_graphics_item import (
        NodeGraphicsItem,
    )

    node = code(design.current_module)
    item = node.input_sockets["data_in"].graphics_item

    assert item.boundingRect().right() <= NodeGraphicsItem.SOCKET_GUTTER


def test_the_bounding_rect_covers_the_label(design):
    """Otherwise the text is clipped away by the socket's own small rect."""
    node = code(design.current_module)
    item = node.input_sockets["data_in"].graphics_item

    assert item.boundingRect().width() > 2 * item.RADIUS


# --- icons ------------------------------------------------------------------


@pytest.mark.parametrize("gate", ["not", "and2", "or2", "xor2"])
def test_every_gate_ships_a_readable_icon(gate):
    from PyQt5.QtSvg import QSvgRenderer

    definition = library().require(f"logic.{gate}")

    assert definition.icon_path is not None
    assert QSvgRenderer(definition.icon_path).isValid()


def test_an_icon_resolves_relative_to_its_definition_file():
    definition = library().require("logic.and2")

    assert definition.icon == "icons/and2.svg"
    assert definition.icon_path.endswith("builtin/logic/icons/and2.svg")


def test_a_missing_icon_file_resolves_to_nothing():
    """A definition naming an icon that is not there must not crash the editor."""
    definition = BlockDefinition(
        id="x",
        label="X",
        kind=BlockKind.HIERARCHICAL,
        icon="nowhere.svg",
        source_path="/tmp/x.block.yml",
    )

    assert definition.icon_path is None


def test_a_definition_without_an_icon_has_no_path():
    assert library().require("builtin.code").icon_path is None


def test_a_gate_node_shows_its_icon(design):
    gate = design.instantiate(library().require("logic.and2"))

    assert gate.content_widget.icon is not None


def test_the_icon_follows_the_theme(design):
    """Qt cannot resolve ``currentColor``, so it is substituted before loading."""
    gate = design.instantiate(library().require("logic.and2"))
    widget = gate.content_widget
    mode = theme_manager().mode

    try:
        theme_manager().apply(ThemeMode.DARK, persist=False)
        assert DARK_THEME.node_title_text.name() in widget._themed_icon()

        theme_manager().apply(ThemeMode.LIGHT, persist=False)
        themed = widget._themed_icon()
        assert LIGHT_THEME.node_title_text.name() in themed
        assert "currentColor" not in themed
    finally:
        theme_manager().apply(mode, persist=False)
