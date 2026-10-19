"""Numbering blocks that would otherwise share a name."""

import pytest

from amaranth_companion.blocks.library import library
from amaranth_companion.design import Design
from amaranth_companion.module.instantiate import instantiate
from amaranth_companion.module.naming import (
    disambiguate,
    in_family,
    index_in_family,
)
from amaranth_companion.windows.main_window import MainWindow


@pytest.fixture
def design(qapp):
    return Design()


def titles(module):
    return sorted(node.title for node in module.nodes.values())


def gate(module, count=1):
    return [
        instantiate(module, library().require("logic.and2"), pos=(200 * i, 0))
        for i in range(count)
    ]


# --- the family ------------------------------------------------------------


@pytest.mark.parametrize(
    "title, base, expected",
    [
        ("AND", "AND", True),
        ("AND0", "AND", True),
        ("AND12", "AND", True),
        ("ANDy", "AND", False),
        ("AN", "AND", False),
        ("XOR", "AND", False),
    ],
)
def test_the_family_is_the_name_with_a_counter(title, base, expected):
    assert in_family(title, base) is expected


def test_a_base_keeps_its_own_digits():
    """A block labelled "and2" is its own family, not a numbered "and"."""
    assert in_family("and2", "and2")
    assert not in_family("and2", "and2x")


@pytest.mark.parametrize(
    "title, expected", [("AND", None), ("AND0", 0), ("AND7", 7), ("AND13", 13)]
)
def test_the_index_comes_off_the_end(title, expected):
    assert index_in_family(title, "AND") == expected


# --- numbering on arrival ---------------------------------------------------


def test_the_first_block_is_not_numbered(design):
    gate(design.current_module)

    assert titles(design.current_module) == ["AND"]


def test_the_second_numbers_them_both(design):
    """The one already there has to make room."""
    module = design.current_module
    gate(module, 2)

    assert titles(module) == ["AND0", "AND1"]


def test_the_count_keeps_going(design):
    module = design.current_module
    gate(module, 5)

    assert titles(module) == ["AND0", "AND1", "AND2", "AND3", "AND4"]


def test_a_different_block_is_left_alone(design):
    module = design.current_module
    gate(module, 2)
    instantiate(module, library().require("logic.xor2"), pos=(0, 300))

    assert titles(module) == ["AND0", "AND1", "XOR"]


def test_a_gap_is_filled_before_counting_on(design):
    """Deleting AND0 and dropping another should reuse 0, not reach for 2."""
    module = design.current_module
    first, _second = gate(module, 2)
    module.remove_node(first)

    gate(module)

    assert titles(module) == ["AND0", "AND1"]


def test_a_renamed_block_frees_its_name(design):
    module = design.current_module
    (first,) = gate(module)
    first.title = "The Important One"

    gate(module)

    assert titles(module) == ["AND", "The Important One"]


def test_a_hand_numbered_block_is_counted_as_one(design):
    """Numbering must not hand out a name that is already taken."""
    module = design.current_module
    (first,) = gate(module)
    first.title = "AND1"

    gate(module)

    assert titles(module) == ["AND0", "AND1"]


def test_ports_are_not_numbered(design):
    """A port's title is its name, which the port block itself owns."""
    module = design.current_module
    for index in range(2):
        instantiate(module, library().require("builtin.port_in"), pos=(0, 300 * index))

    assert titles(module) == ["Input", "Input"]


def test_each_module_counts_for_itself(design):
    """Numbering is about one canvas; a child graph is a different one."""
    module = design.current_module
    (first,) = gate(module)
    design.enter(first)

    (inside,) = gate(design.current_module)

    assert inside.title == "AND"
    assert titles(module) == ["AND"]


def test_an_untitled_block_is_left_alone(design):
    module = design.current_module
    (node,) = gate(module)
    node.title = ""

    assert disambiguate(module, node) == []


def test_the_nodes_that_moved_are_reported(design):
    module = design.current_module
    (first,) = gate(module)
    (second,) = gate(module)

    # `second` renamed itself; `first` is the one that had to make room
    assert second.title == "AND1"
    assert first.title == "AND0"


# --- through the editor -----------------------------------------------------


@pytest.fixture
def window(qapp):
    window = MainWindow()
    window.new_file()
    yield window
    window.close()


def test_dropping_a_second_block_numbers_both(window):
    from PyQt5.QtCore import QPointF

    window.drop_block("logic.and2", QPointF(0, 0))
    window.drop_block("logic.and2", QPointF(400, 0))

    assert titles(window.current_module) == ["AND0", "AND1"]


def test_undoing_the_arrival_undoes_the_renaming(window):
    """The rename is part of the same edit, so it goes back with it."""
    window.insert_block("logic.and2")
    window.insert_block("logic.and2")

    window.undo()

    assert titles(window.current_module) == ["AND"]


def test_the_tree_shows_the_new_numbers(window):
    window.insert_block("logic.and2")
    window.insert_block("logic.and2")

    root = window._hierarchy.tree.topLevelItem(0)
    rows = sorted(root.child(i).text(0) for i in range(root.childCount()))

    assert rows == ["AND0", "AND1"]


# --- what the numbering means in generated code -----------------------------


def test_the_class_is_named_after_the_block(design):
    """Numbered instances are still one kind of block, so one class."""
    from amaranth_companion.generate.python import generate_source

    gate(design.current_module, 2)
    source = generate_source(design)

    assert source.count("class AND(Elaboratable):") == 1
    assert "class AND0(Elaboratable):" not in source


def test_the_instances_are_named_after_the_blocks(design):
    from amaranth_companion.generate.python import generate_source

    gate(design.current_module, 2)
    source = generate_source(design)

    assert "and0 = AND(" in source
    assert "and1 = AND(" in source
    assert source.count("class AND(Elaboratable):") == 1


def test_a_renamed_block_names_its_own_class(design):
    """A counter is stripped; a name the user chose is not."""
    from amaranth_companion.generate.python import generate_source
    from amaranth_companion.module.naming import family_name

    (node,) = gate(design.current_module)
    node.title = "Half Adder"

    assert family_name(node) == "Half Adder"
    assert "class HalfAdder(Elaboratable):" in generate_source(design)
