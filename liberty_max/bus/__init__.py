"""Message bus module for decoupled channel-agent communication."""

from liberty_max.bus.events import InboundMessage, OutboundMessage
from liberty_max.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
