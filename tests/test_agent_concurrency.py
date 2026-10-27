"""Runs of one agent never wait for one another (the live benchmark found chats
queued 72-191 s behind other runs of the same agent for 29 ms of work)."""

import asyncio
from types import MethodType

from agents import base


def make_agent():
    agent = base.BaseAgent(name="Concurrency test", config={"model": "configured"})
    release = asyncio.Event()

    async def impl(self, task, *args):
        self.total_tasks += 1
        self._faculty_guidance = f"guidance for {task}"
        if task == "slow":
            await release.wait()
        return {"result": task, "success": True}

    agent._execute_impl = MethodType(impl, agent)
    return agent, release


async def test_a_second_run_does_not_wait_for_the_first():
    agent, release = make_agent()
    started = agent.total_tasks
    slow = asyncio.create_task(agent.execute("slow"))
    await asyncio.sleep(0.05)
    assert agent.state == "acting" and agent.current_task == "slow"
    quick = await asyncio.wait_for(agent.execute("quick"), 1)
    assert quick["result"] == "quick"
    assert quick["usage"]["timings"]["queue_wait_ms"] < 500
    assert agent.state == "acting"  # the slow run is still going
    release.set()
    assert (await slow)["result"] == "slow"
    # What each run added is kept on the agent; nothing is left running.
    assert agent.total_tasks == started + 2
    assert agent.state == "resting" and agent.current_task is None


async def test_each_run_keeps_its_own_state_and_tools():
    agent, release = make_agent()
    release.set()
    await agent.execute("first")
    assert agent._faculty_guidance == "guidance for first"  # the last run's trace
    run = agent._run_copy()
    # The tool table is bound to the run, so a tool sees the run's own model.
    bound = [tool for tool in run.tools.values() if hasattr(tool, "__self__")]
    assert bound and all(tool.__self__ is run for tool in bound)
    assert run.config is not agent.config and run.config == agent.config


async def test_a_settings_change_waits_only_for_the_copy_not_the_run():
    agent, release = make_agent()
    slow = asyncio.create_task(agent.execute("slow"))
    await asyncio.sleep(0.05)
    async with asyncio.timeout(1):
        async with agent._execution_lock:  # what a settings change takes
            agent.config["system_prompt"] = "changed"
    release.set()
    await slow
