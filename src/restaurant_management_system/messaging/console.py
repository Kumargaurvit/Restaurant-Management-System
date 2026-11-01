import logging

logger = logging.getLogger("messaging.console")


class ConsoleProvider:
    """Stand-in provider that only logs. Used until a WhatsApp provider is chosen."""

    async def send_text(self, phone: str, text: str) -> None:
        logger.info("WhatsApp to %s: %s", phone, text)
