from typing import Optional, Protocol


class Messenger(Protocol):
    async def handle_update(self, payload: dict) -> Optional[str]:
        """Process one inbound message and reply"""
        ...

    async def send_message(self, chat_id, text) -> None:
        """Send an outbound message to the platform user."""
        ...