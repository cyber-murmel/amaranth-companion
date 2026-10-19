"""Choosing a board, binding ports to its IOs, and building a bitstream.

The checks that actually synthesise are skipped without the FPGA toolchain,
and the Glasgow ones without the ``glasgow`` package -- it is not a hard
dependency, because most boards come from ``amaranth-boards``.
"""

import shutil
import sys

import pytest

from amaranth_companion import platforms
from amaranth_companion.blocks.definition import BlockKind
from amaranth_companion.blocks.library import library
from amaranth_companion.design import Design
from amaranth_companion.examples import find, open_example
from amaranth_companion.generate import generate_files, generate_source
from amaranth_companion.module.element import Edge
from amaranth_companion.module.instantiate import instantiate, refresh_node_ports
from amaranth_companion.verify import PlatformMissing, ToolchainMissing, run_build
from amaranth_companion.verify.hardware import (
    load_platform,
    missing_tools,
    required_tools,
)

GLASGOW = "glasgow.hardware.platform.rev_c:GlasgowRevC123Platform"
ICEBREAKER = "amaranth_boards.icebreaker:ICEBreakerPlatform"


def have(platform_id):
    return platforms.find(platform_id) is not None


needs_glasgow = pytest.mark.skipif(
    not have(GLASGOW), reason="needs the glasgow package"
)
needs_toolchain = pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("yosys", "nextpnr-ice40", "icepack")),
    reason="needs yosys, nextpnr-ice40 and icepack",
)


@pytest.fixture
def design(qapp):
    return Design()


# --- discovering boards -----------------------------------------------------


def test_boards_are_discovered():
    found = platforms.list_platforms()

    assert len(found) > 50
    assert any(spec.vendor == "amaranth_boards" for spec in found)


def test_every_shipped_board_module_contributes():
    """A board that silently fails the filter is a board nobody can pick."""
    import pkgutil

    import amaranth_boards

    modules = {
        info.name
        for info in pkgutil.iter_modules(amaranth_boards.__path__)
        if not info.name.startswith("_")
    } - platforms.SKIP_MODULES

    covered = {
        spec.module.split(".")[-1]
        for spec in platforms.list_platforms()
        if spec.vendor == "amaranth_boards"
    }

    assert modules == covered


def test_gowin_boards_are_included():
    """They name their chip `part`, not `device`; an early filter dropped them."""
    labels = [spec.label for spec in platforms.list_platforms()]

    assert any("Tang" in label for label in labels)


def test_vendor_base_classes_are_not_offered():
    """`SiliconBluePlatform` is not a board you can build for."""
    ids = [spec.id for spec in platforms.list_platforms()]

    assert not any(spec.endswith(":SiliconBluePlatform") for spec in ids)
    assert not any(":_" in spec for spec in ids)


def test_a_platform_can_be_loaded():
    spec = platforms.find(ICEBREAKER)

    assert spec is not None
    assert spec.load().__name__ == "ICEBreakerPlatform"


def test_an_unknown_platform_is_refused():
    with pytest.raises(KeyError):
        platforms.load("nope:NotAPlatform")


# --- what a board offers ----------------------------------------------------


def test_a_board_reports_its_ios():
    ios = platforms.list_ios(ICEBREAKER)

    assert any(spec.id == "led 0" for spec in ios)
    assert any(spec.id == "button 0" for spec in ios)


def test_io_directions_come_from_the_board():
    button = platforms.find_io(ICEBREAKER, "button 0")
    led = platforms.find_io(ICEBREAKER, "led 0")

    assert button.direction == "i"
    assert led.direction == "o"


@needs_glasgow
def test_a_glasgow_led_is_reachable_whatever_the_revision_calls_it():
    """Older Glasgow packages offer `led 0`; newer ones claim it and give
    `LED0`. Either way a design must be able to drive an LED."""
    spec = platforms.find_io(GLASGOW, "LED0")

    assert spec is not None
    assert platforms.effective_direction(spec, None) == "o"


def test_an_uninstallable_board_reports_no_ios():
    assert platforms.list_ios("nope:NotAPlatform") == ()


@pytest.mark.parametrize(
    "text, expected",
    [("LED0", ("LED0", None)), ("led 0:i", ("led 0", "i")), ("a b", ("a b", None))],
)
def test_a_direction_can_be_spelled_out(text, expected):
    assert platforms.parse_io(text) == expected


def test_a_bidirectional_io_is_driven_by_default():
    """An LED or a port pin is usually something a design drives."""
    bidir = platforms.IOSpec(id="x", kind=platforms.IOKind.NAMED, direction="io")

    assert platforms.effective_direction(bidir, None) == "o"
    assert platforms.effective_direction(bidir, "i") == "i"


# --- choosing one -----------------------------------------------------------


def test_a_design_has_no_board_by_default(design):
    assert design.platform is None
    assert "platform" not in design.to_dict()


def test_a_chosen_board_round_trips(design):
    design.platform = ICEBREAKER

    restored = Design()
    restored.load(design.to_dict())

    assert restored.platform == ICEBREAKER


def test_a_board_can_be_cleared(design):
    design.platform = ICEBREAKER
    design.platform = None

    assert "platform" not in design.to_dict()


# --- resource blocks --------------------------------------------------------


def resource(design, text, **kwargs):
    node = instantiate(
        design.current_module,
        library().require("builtin.resource"),
        text=text,
        **kwargs,
    )
    refresh_node_ports(node)
    return node


def test_an_output_io_gives_the_block_an_input(design):
    """The design drives an LED, so the block takes a signal."""
    design.platform = ICEBREAKER
    node = resource(design, "led 0")

    assert list(node.input_sockets) == ["led_0_in"]
    assert not node.output_sockets


def test_an_input_io_gives_the_block_an_output(design):
    design.platform = ICEBREAKER
    node = resource(design, "button 0")

    assert list(node.output_sockets) == ["button_0_out"]
    assert not node.input_sockets


def test_a_direction_override_is_honoured(design):
    design.platform = ICEBREAKER
    node = resource(design, "uart 0:i")

    assert list(node.output_sockets) == ["uart_0_out"]


def test_an_io_the_board_does_not_have_is_reported(design):
    design.platform = ICEBREAKER
    node = resource(design, "nonexistent 3")

    assert "not an io on this board" in node.error


def test_a_board_problem_never_drops_the_wiring(design):
    """Opening a design without the board's package must not edit it.

    The port survives, so the edge into it survives, so saving afterwards
    does not quietly delete the connection.
    """
    design.platform = ICEBREAKER
    node = resource(design, "led 0")
    module = design.current_module
    code = instantiate(
        module,
        library().require("builtin.code"),
        text=(
            "from amaranth import *\n\n\n"
            "class Driver(Elaboratable):\n"
            "    def __init__(self):\n"
            "        self.q_out = Signal(1)\n"
            "    def elaborate(self, platform):\n"
            "        return Module()\n"
        ),
        pos=(-400, 0),
    )
    assert module.add_edge(
        Edge(code.output_sockets["q_out"], node.input_sockets["led_0_in"])
    )

    # as if the board's package were not installed on this machine
    design.platform = "not_installed.at_all:SomePlatform"
    refresh_node_ports(node)

    assert list(node.input_sockets) == ["led_0_in"]
    assert len(list(module.edges)) == 1
    assert "not installed" in node.error


def test_an_unknown_io_still_leaves_something_to_wire_to(design):
    """Retyping the io is a rename, so the port follows what was typed.

    It is flagged, but the block keeps a port: a block with no socket at all
    cannot be reconnected without deleting and replacing it.
    """
    design.platform = ICEBREAKER
    node = resource(design, "led 0")

    node.text = "led 99"
    refresh_node_ports(node)

    assert list(node.input_sockets) == ["led_99_in"]
    assert "not an io on this board" in node.error


def test_a_resource_block_without_a_board_says_so(design):
    node = resource(design, "led 0")

    assert "no board chosen" in node.error


def test_an_empty_resource_block_asks_to_be_filled_in(design):
    node = resource(design, "")

    assert node.error
    assert not list(node.sockets)


def test_a_resource_block_round_trips(design):
    design.platform = ICEBREAKER
    resource(design, "led 0")

    restored = Design()
    restored.load(design.to_dict())
    node = next(iter(restored.root.nodes.values()))

    assert node.kind is BlockKind.RESOURCE
    assert node.text == "led 0"


# --- generating the binding -------------------------------------------------


def wired_design(qapp, platform_id, io_text):
    """A code block driving a resource block."""
    design = Design()
    design.platform = platform_id
    module = design.current_module

    code = instantiate(
        module,
        library().require("builtin.code"),
        text=(
            "from amaranth import *\n\n\n"
            "class Driver(Elaboratable):\n"
            "    def __init__(self):\n"
            "        self.q_out = Signal(1)\n"
            "    def elaborate(self, platform):\n"
            "        m = Module()\n"
            "        m.d.comb += self.q_out.eq(1)\n"
            "        return m\n"
        ),
    )
    pin = resource(design, io_text, pos=(400, 0))
    socket = next(iter(pin.input_sockets.values()))
    assert module.add_edge(Edge(code.output_sockets["q_out"], socket))

    return design


def test_a_requested_resource_generates_a_request(qapp):
    source = generate_source(wired_design(qapp, ICEBREAKER, "led 0"))

    assert 'platform.request("led", 0, dir="-")' in source
    assert 'io.Buffer("o"' in source


def expected_port_expression(platform_id: str, io_text: str) -> str:
    """How the generator should reach the io this board resolved ``io_text`` to."""
    from amaranth_companion.generate.python import DesignGenerator

    spec = platforms.find_io(platform_id, io_text)
    return DesignGenerator._port_expression(
        spec, io_text, platforms.NAMED_PORTS_ATTRIBUTE
    )


@needs_glasgow
def test_a_glasgow_binding_follows_the_installed_revision(qapp):
    """The block says `LED0`; the call depends on which package is installed."""
    source = generate_source(wired_design(qapp, GLASGOW, "LED0"))

    assert expected_port_expression(GLASGOW, "LED0") in source
    assert 'io.Buffer("o", ' in source


def test_the_binding_is_guarded(qapp):
    """The same design is simulated and proved with no platform at all."""
    source = generate_source(wired_design(qapp, ICEBREAKER, "led 0"))

    assert "if platform is not None:" in source


def test_the_io_import_is_only_added_when_used(qapp, design):
    design.instantiate(library().require("logic.and2"))

    assert "from amaranth.lib import io" not in generate_source(design)


def test_an_unconnected_resource_block_generates_nothing(qapp, design):
    design.platform = ICEBREAKER
    resource(design, "led 0")

    assert "io.Buffer" not in generate_source(design)


def test_a_bound_design_still_simulates(qapp):
    """Binding to a pin must not break the simulation path."""
    from amaranth.sim import Simulator

    design = wired_design(qapp, ICEBREAKER, "led 0")
    namespace: dict = {}
    exec(compile(generate_source(design), "<generated>", "exec"), namespace)

    simulator = Simulator(namespace["Top"]())
    simulator.run()


# --- building ---------------------------------------------------------------


def test_required_tools_come_from_the_platform():
    platform = platforms.load(ICEBREAKER)()

    assert "yosys" in required_tools(platform)
    assert "nextpnr-ice40" in required_tools(platform)


def test_a_missing_board_package_is_named():
    with pytest.raises(PlatformMissing) as caught:
        load_platform("not_a_package.at_all:SomePlatform")

    assert "not_a_package" in str(caught.value)


def test_a_malformed_platform_name_is_refused():
    with pytest.raises(PlatformMissing):
        load_platform("missing-the-separator")


def test_building_without_a_board_is_refused(qapp, design):
    result = run_build(design)

    assert not result.ok
    assert result.unavailable
    assert "does not name a board" in result.error


def test_a_missing_toolchain_raises_rather_than_half_building(monkeypatch):
    import amaranth_companion.verify.hardware as hardware

    monkeypatch.setattr(hardware, "missing_tools", lambda platform: ["yosys"])

    with pytest.raises(ToolchainMissing) as caught:
        hardware.build(object(), ICEBREAKER)

    assert "yosys" in str(caught.value)


def test_a_missing_toolchain_comes_back_as_unavailable(qapp, monkeypatch, tmp_path):
    """The worker turns it into a result, not a traceback.

    Exercised in-process: `run_build` spawns a subprocess, which would not
    see a patch applied here.
    """
    import amaranth_companion.verify.builds as builds
    import amaranth_companion.verify.hardware as hardware

    monkeypatch.setattr(hardware, "missing_tools", lambda platform: ["yosys"])
    design = wired_design(qapp, ICEBREAKER, "led 0")

    response = builds.run(
        generate_source(design), "Top", ICEBREAKER, str(tmp_path), False, "top"
    )

    assert not response["ok"]
    assert response["unavailable"]
    assert "yosys" in response["error"]


def test_a_toolchain_check_names_what_is_absent():
    platform = platforms.load(ICEBREAKER)()

    absent = missing_tools(platform)

    assert all(tool in required_tools(platform) for tool in absent)


# --- the shipped glasgow example --------------------------------------------


@needs_glasgow
def test_the_glasgow_example_names_a_board(qapp):
    design = open_example(find("glasgow-blink"))

    assert design.platform == GLASGOW


@needs_glasgow
def test_the_glasgow_example_binds_to_an_led(qapp):
    design = open_example(find("glasgow-blink"))

    pin = next(
        node for node in design.root.nodes.values() if node.kind is BlockKind.RESOURCE
    )
    assert pin.text == "LED0"
    assert not pin.error
    assert list(pin.input_sockets) == ["led0_in"]


@needs_glasgow
def test_the_glasgow_example_generates_a_pin_binding(qapp):
    design = open_example(find("glasgow-blink"))
    source = generate_source(design)

    port = expected_port_expression(design.platform, "LED0")
    assert f'io.Buffer("o", {port})' in source
    assert "led0.o.eq(self.blinker.blink_out)" in source


@needs_glasgow
def test_the_generated_package_carries_the_board(qapp):
    files = generate_files(open_example(find("glasgow-blink")), "blink")

    assert "blink/_hardware.py" in files
    assert GLASGOW in files["blink/__main__.py"]
    assert "amaranth_companion" not in "".join(files.values())


@needs_glasgow
@needs_toolchain
def test_the_glasgow_example_builds_a_bitstream(qapp, tmp_path):
    """The end of the chain: canvas -> amaranth -> iCE40 bitstream."""
    design = open_example(find("glasgow-blink"))

    result = run_build(design, directory=tmp_path)

    assert result.ok, result.error
    bitstream = tmp_path / "untitled.bin"
    assert bitstream.stat().st_size > 1000
    # iCE40 bitstreams start with this sync pattern
    assert bitstream.read_bytes()[:4] == b"\xff\x00\x00\xff"


def test_an_uninstalled_board_is_not_a_warning(caplog):
    """A design naming a board this machine lacks is expected, not broken.

    The resource blocks say so on the canvas; repeating it as a warning in
    the log is noise, and the message used to be tautological besides.
    """
    import logging

    platforms.list_ios.cache_clear()
    with caplog.at_level(logging.WARNING, logger="amaranth_companion.platforms"):
        assert platforms.list_ios("not_installed.at_all:SomePlatform") == ()

    assert caplog.records == []


# --- surviving a board package update ---------------------------------------


@pytest.mark.parametrize(
    "spelling, normalised",
    [("LED0", "led0"), ("led 0", "led0"), ("port_a 3", "porta3"), ("A7", "a7")],
)
def test_io_spellings_normalise_together(spelling, normalised):
    assert platforms.normalise_io(spelling) == normalised


def test_an_io_resolves_across_spellings():
    """Glasgow used to offer `led 0`; it now claims it and offers `LED0`.

    A design drawn against one revision must not break against the other.
    """
    exact = platforms.find_io(ICEBREAKER, "led 0")
    spelled_differently = platforms.find_io(ICEBREAKER, "LED0")

    assert exact is not None
    assert spelled_differently is exact


def test_an_exact_match_wins_over_a_spelling_match():
    ios = platforms.list_ios(ICEBREAKER)
    assert any(spec.id == "led 0" for spec in ios)

    assert platforms.find_io(ICEBREAKER, "led 0").id == "led 0"


def test_a_genuinely_absent_io_still_returns_nothing():
    assert platforms.find_io(ICEBREAKER, "trumpet 9") is None


@pytest.mark.parametrize(
    "kind, expected",
    [
        (platforms.IOKind.REQUEST, 'platform.request("led", 0, dir="-")'),
        (platforms.IOKind.NAMED, 'platform.glasgow_pins["LED0"]'),
    ],
)
def test_the_generated_call_follows_the_resolved_io(kind, expected):
    """The block says `LED0`; what gets generated depends on the board."""
    from amaranth_companion.generate.python import DesignGenerator

    spec = platforms.IOSpec(
        id="led 0" if kind is platforms.IOKind.REQUEST else "LED0",
        kind=kind,
        name="led",
        number=0,
        direction="o",
    )

    assert (
        DesignGenerator._port_expression(spec, "LED0", platforms.NAMED_PORTS_ATTRIBUTE)
        == expected
    )


# --- loading a bitstream onto a board ---------------------------------------


FAKE_PLATFORM = '''
class Platform:
    """A platform that programs the way Glasgow's does."""

    required_tools = ()
    calls = 0

    def toolchain_program(self, products, name):
        type(self).calls += 1

        async def do_program():
            return products, name

        return asyncio.get_event_loop().run_until_complete(do_program())
'''


def fake_platform_module(name: str, *, import_asyncio: bool):
    """A module holding a platform, optionally forgetting to import asyncio.

    Glasgow's own revision forgets, which is the case being covered; the
    module is built here rather than imported so the test does not depend on
    which revision happens to be installed.
    """
    import sys
    import types

    module = types.ModuleType(name)
    source = ("import asyncio\n" if import_asyncio else "") + FAKE_PLATFORM
    exec(compile(source, name, "exec"), module.__dict__)
    sys.modules[name] = module
    return module


@pytest.fixture
def forgetful(request):
    """A platform whose module uses asyncio without importing it."""
    import sys

    name = f"_fake_platform_{request.node.name}"
    module = fake_platform_module(name, import_asyncio=False)
    yield module.Platform()
    del sys.modules[name]


@pytest.fixture
def careful(request):
    import sys

    name = f"_fake_careful_{request.node.name}"
    module = fake_platform_module(name, import_asyncio=True)
    yield module.Platform()
    del sys.modules[name]


def test_an_event_loop_is_ready_for_the_programmer(careful):
    """A board reached over USB is reached through asyncio.

    ``get_event_loop`` used to make a loop on demand and now raises instead,
    which is not something a platform can be expected to have known.
    """
    from amaranth_companion.verify.hardware import program_board

    program_board(careful, {"top.bin": b""}, "top")

    assert type(careful).calls == 1


def test_a_forgotten_import_is_supplied(forgetful):
    """Glasgow's platform uses asyncio in a module that never imports it."""
    from amaranth_companion.verify.hardware import program_board

    program_board(forgetful, {"top.bin": b""}, "top")

    # called twice: once to find out, once after supplying the name
    assert type(forgetful).calls == 2
    assert hasattr(sys.modules[type(forgetful).__module__], "asyncio")


def test_a_name_that_is_not_a_module_still_fails(careful):
    from amaranth_companion.verify.hardware import ProgrammingFailed, program_board

    def nonsense(products, name):
        raise NameError("name 'wat' is not defined", name="wat")

    careful.toolchain_program = nonsense

    with pytest.raises(ProgrammingFailed, match="wat"):
        program_board(careful, {}, "top")


def test_a_programming_failure_keeps_the_bitstream(careful):
    from amaranth_companion.verify.hardware import ProgrammingFailed, program_board

    def unplugged(products, name):
        raise FileNotFoundError("no such device")

    careful.toolchain_program = unplugged

    with pytest.raises(ProgrammingFailed) as raised:
        program_board(careful, {}, "top", bitstream="/tmp/blink.bin")

    assert raised.value.bitstream == "/tmp/blink.bin"
    assert "FileNotFoundError" in str(raised.value)


def test_a_running_loop_is_left_alone(careful):
    """Nothing to arrange when the caller is already inside a loop."""
    import asyncio

    from amaranth_companion.verify.hardware import ProgrammingFailed, program_board

    async def inside():
        # get_event_loop inside a running loop returns the running one, which
        # cannot be run again -- the point is that we do not replace it
        with pytest.raises(ProgrammingFailed):
            program_board(careful, {}, "top")

    asyncio.run(inside())


# --- what the editor reports -------------------------------------------------


def test_an_unreachable_board_is_reported_as_such():
    from amaranth_companion.verify.builds import BuildResult

    result = BuildResult(
        ok=True,
        bitstream="/tmp/build/blink.bin",
        programmed=False,
        error="FileNotFoundError: no such device",
    )

    assert "Built blink.bin" in result.summary
    assert "could not program the board" in result.summary


def test_a_programmed_board_says_so():
    from amaranth_companion.verify.builds import BuildResult

    result = BuildResult(ok=True, bitstream="/tmp/build/blink.bin", programmed=True)

    assert result.summary == "Built and programmed blink.bin"
