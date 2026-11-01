from typing import Protocol


class MessageProvider(Protocol):
    """Sends a WhatsApp text to a guest. Real providers (Gupshup, Wati, ...) implement this."""

    async def send_text(self, phone: str, text: str) -> None: ...
