"""Project scope survives async work and never leaks between concurrent chats."""

import asyncio

from workspace.context import bind_workspace, bound_workspace_id, reset_workspace


async def test_bound_workspace_is_private_to_each_chat_and_reset():
    first_bound = asyncio.Event()
    second_bound = asyncio.Event()

    async def chat(project, ready, other_ready):
        token = bind_workspace(project)
        try:
            ready.set()
            await other_ready.wait()
            assert bound_workspace_id() == project
            assert await asyncio.to_thread(bound_workspace_id) == project
        finally:
            reset_workspace(token)
        assert bound_workspace_id() is None

    await asyncio.gather(
        chat("project-a", first_bound, second_bound),
        chat("project-b", second_bound, first_bound),
    )
    assert bound_workspace_id() is None


def test_nested_scope_restores_outer_selection_on_failure():
    outer = bind_workspace("outer-project")
    try:
        inner = bind_workspace("inner-project")
        try:
            assert bound_workspace_id() == "inner-project"
        finally:
            reset_workspace(inner)
        assert bound_workspace_id() == "outer-project"
    finally:
        reset_workspace(outer)
    assert bound_workspace_id() is None
