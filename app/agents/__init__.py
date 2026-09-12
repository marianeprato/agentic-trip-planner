"""Wires the star handoff topology.

triage_agent is defined with handoffs=[] because Budget/Local Recs each
need a handoff *back* to Triage (import them and this would be circular).
Importing them here and then appending completes both directions without
a circular import.
"""

from agents import handoff

from app.agents.budget_agent import budget_agent
from app.agents.local_recs_agent import local_recs_agent
from app.agents.triage_agent import triage_agent

triage_agent.handoffs = [handoff(budget_agent), handoff(local_recs_agent)]

__all__ = ["triage_agent", "budget_agent", "local_recs_agent"]
