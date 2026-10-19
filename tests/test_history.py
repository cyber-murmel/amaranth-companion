from amaranth_companion.module.element import Edge


def test_a_fresh_module_has_nothing_to_undo(module):
    assert not module.history.is_undoable
    assert not module.history.is_redoable


def test_check_in_ignores_an_unchanged_state(chain):
    module, _ = chain

    module.history.check_in()
    module.history.check_in()

    assert not module.history.is_undoable


def test_undo_restores_a_node_position(chain):
    module, nodes = chain
    uuid = nodes[0].uuid

    nodes[0].pos = (500.0, 500.0)
    module.history.check_in()
    assert module.history.is_undoable

    module.history.undo()

    assert module.nodes[uuid].pos == (0.0, 0.0)


def test_redo_reapplies_the_undone_change(chain):
    module, nodes = chain
    uuid = nodes[0].uuid
    nodes[0].pos = (500.0, 500.0)
    module.history.check_in()
    module.history.undo()

    assert module.history.is_redoable
    module.history.redo()

    assert module.nodes[uuid].pos == (500.0, 500.0)
    assert not module.history.is_redoable


def test_undo_restores_a_deleted_node_and_its_edges(chain):
    module, nodes = chain

    module.remove_node(nodes[1])
    module.history.check_in()
    assert len(module.nodes) == 2
    assert list(module.edges) == []

    module.history.undo()

    assert len(module.nodes) == 3
    assert len(list(module.edges)) == 2


def test_undo_is_bounded_by_the_oldest_snapshot(chain):
    module, nodes = chain

    for _ in range(5):
        module.history.undo()

    assert len(module.nodes) == 3
    assert not module.history.is_undoable


def test_a_new_change_discards_the_redo_stack(chain):
    module, nodes = chain
    nodes[0].pos = (500.0, 500.0)
    module.history.check_in()
    module.history.undo()
    assert module.history.is_redoable

    next(iter(module.nodes.values())).pos = (100.0, 100.0)
    module.history.check_in()

    assert not module.history.is_redoable


def test_restoring_does_not_record_a_snapshot(chain):
    module, nodes = chain
    nodes[0].pos = (500.0, 500.0)
    module.history.check_in()

    module.history.undo()

    # if the rebuild had checked itself in, redo would have been discarded
    assert module.history.is_redoable
    assert not module.history.is_undoable


def test_reset_makes_the_current_state_the_baseline(chain, make_node):
    module, _ = chain
    make_node(module, title="added")

    module.history.reset()

    assert not module.history.is_undoable
    assert not module.history.is_redoable
    assert len(module.nodes) == 4


def test_history_tracks_added_edges(chain, make_node):
    module, nodes = chain
    extra = make_node(module, title="extra")
    module.history.check_in()

    module.add_edge(Edge(extra.output_sockets["o_out"], nodes[0].input_sockets["b_in"]))
    module.history.check_in()
    assert len(list(module.edges)) == 3

    module.history.undo()

    assert len(list(module.edges)) == 2
