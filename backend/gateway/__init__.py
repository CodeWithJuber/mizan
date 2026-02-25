"""
MIZAN Gateway (Bab - بَاب — Gate)
====================================

"Enter upon them through the gate (Bab)" — Quran 5:23

Multi-channel gateway routing messages through QuranicMessage format.
Each channel is a Bab (gate) into the MIZAN system.
"""

from .bab import MizanGateway, GatewayConfig
from .channels.base import ChannelAdapter, IncomingMessage
