from . import agent  # noqa: F401 — ensures root_agent is importable by adk run

from .agent import root_agent

__all__ = ["root_agent"]
