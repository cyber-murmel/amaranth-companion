from amaranth_companion.module.element import Edge, SocketType


def test_add_node_registers_it_by_uuid(module, make_node):
    node = make_node(module, title="n")

    assert module.nodes == {node.uuid: node}
    assert node.graphics_item in module.scene.items()


def test_add_edge_accepts_output_to_input(module, make_node):
    source, sink = make_node(module), make_node(module)

    edge = Edge(source.output_sockets["o"], sink.input_sockets["a"])

    assert module.add_edge(edge) is True
    assert list(module.edges) == [edge]


def test_add_edge_rejects_wrong_direction(module, make_node):
    first, second = make_node(module), make_node(module)

    # input -> input is not a connection
    edge = Edge(first.input_sockets["a"], second.input_sockets["b"])

    assert module.add_edge(edge) is False
    assert list(module.edges) == []
    # the rejected edge must not stay registered on its sockets
    assert first.input_sockets["a"].edges == []
    assert second.input_sockets["b"].edges == []


def test_edges_yields_each_edge_once(chain):
    module, _ = chain

    assert len(list(module.edges)) == 2


def test_edges_order_is_stable(chain):
    module, _ = chain

    assert list(module.edges) == list(module.edges)


def test_remove_node_removes_all_of_its_edges(module, make_node):
    """Regression: remove_edge mutates the socket list being iterated."""
    left, middle, right = make_node(module), make_node(module), make_node(module)
    module.add_edge(Edge(left.output_sockets["o"], middle.input_sockets["a"]))
    module.add_edge(Edge(right.output_sockets["o"], middle.input_sockets["b"]))
    module.add_edge(Edge(middle.output_sockets["o"], right.input_sockets["a"]))
    assert len(list(middle.edges)) == 3

    module.remove_node(middle)

    assert list(module.edges) == []
    assert left.output_sockets["o"].edges == []
    assert right.input_sockets["a"].edges == []
    assert right.output_sockets["o"].edges == []


def test_remove_edge_detaches_both_sockets(module, make_node):
    source, sink = make_node(module), make_node(module)
    edge = Edge(source.output_sockets["o"], sink.input_sockets["a"])
    module.add_edge(edge)

    module.remove_edge(edge)

    assert source.output_sockets["o"].edges == []
    assert sink.input_sockets["a"].edges == []
    assert list(module.edges) == []


def test_clear_empties_the_module(chain):
    module, _ = chain

    module.clear()

    assert module.nodes == {}
    assert list(module.edges) == []


def test_node_sockets_cover_inputs_and_outputs(module, make_node):
    node = make_node(
        module,
        inputs={"x": SocketType.BIT},
        outputs={"y": SocketType.BIT, "z": SocketType.BIT},
    )

    assert [socket.name for socket in node.sockets] == ["x", "y", "z"]
    assert all(socket.is_input for socket in node.input_sockets.values())
    assert all(socket.is_output for socket in node.output_sockets.values())


def test_node_title_defaults_to_short_uuid(module, make_node):
    node = make_node(module)

    assert node.title == node.uuid[:8]
