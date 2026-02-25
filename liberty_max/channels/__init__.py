"""Chat channels module with plugin architecture."""

from liberty_max.channels.base import BaseChannel
from liberty_max.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
