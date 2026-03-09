"""Tool for delegating tasks to peer agents via MessageBus."""

from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus


class AgentDelegateTool(Tool):
    """Tool to delegate tasks to peer agents running in the same process."""

    def __init__(self, peer_buses: dict[str, MessageBus], 
                 allowed_agent_delegates: list[str], 
                 peer_profiles: dict[str, str],
                 self_agent_name: str):
        self._buses = peer_buses
        self._allowed = allowed_agent_delegates
        self._profiles = peer_profiles
        self._self_name = self_agent_name
        self._origin_channel = "system"
        self._origin_chat_id = "delegate"

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the calling context so the remote agent knows where to reply."""
        self._origin_channel = channel
        self._origin_chat_id = chat_id

    @property
    def name(self) -> str:
        return "agent_delegate"

    @property
    def description(self) -> str:
        allowed = []
        for name, bus in self._buses.items():
            if "*" in self._allowed or name in self._allowed:
                allowed.append(name)
                
        if not allowed:
            return "No peer agents are available or authorized to be delegated to."

        # Compile the comprehensive manual from peer instances
        manual = []
        for name in allowed:
            prof = self._profiles.get(name, "No description available.")
            manual.append(f"[{name}]\n{prof}")
            
        compiled_manual = "\n---\n".join(manual)
            
        return (
            "Delegate a background task to an independent peer agent.\n"
            "This command asynchronously fires off the task to the peer agent and returns instantly, "
            "allowing you to continue your current work or talk to the user.\n"
            "When the peer agent finishes, their results will be returned as an incoming system text observation "
            "directly into your working memory context.\n\n"
            "AVAILABLE PEER AGENTS (and their capabilities):\n"
            f"{compiled_manual}"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "The exact name of the peer agent to delegate to (e.g. from the list above).",
                },
                "task": {
                    "type": "string",
                    "description": "The specific, detailed task instructions and all relevant context needed for them to operate independently.",
                },
            },
            "required": ["agent_name", "task"],
        }

    async def execute(self, agent_name: str, task: str, **kwargs: Any) -> str:
        """Publish an InboundMessage to the peer agent's MessageBus."""
        if agent_name not in self._buses:
            return f"Error: Peer agent '{agent_name}' not found."
            
        if "*" not in self._allowed and agent_name not in self._allowed:
            return f"Error: You do not have permission to delegate tasks to '{agent_name}'. Allowed: {', '.join(self._allowed)}"

        bus = self._buses[agent_name]
        
        # We spoof the source as "system" so the peer knows it's an internal background task
        # We specify "delegated_from" metadata so that the peer's forwarder intercepts the reply.
        msg = InboundMessage(
            channel="system",
            sender_id="peer_agent",
            chat_id=f"{self._origin_channel}:{self._origin_chat_id}",
            content=task,
            metadata={
                "delegated_from": self._self_name,
            }
        )
        
        await bus.publish_inbound(msg)
        return (
            f"Task successfully delegated to peer agent '{agent_name}'. "
            "You can continue with other work over the user chat. "
            "When the peer finishes, their result will asynchronously arrive back as a new observation in this session."
        )
