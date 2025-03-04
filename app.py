import asyncio
import logging

from logger import setup_logging
from config import Config
from adapter.adapter import TelegramAdapter
from socket_io.server import SocketIOServer

async def main():
    setup_logging()
    logging.info("Starting Telegram adapter")

    socketio_server = SocketIOServer()
    adapter = TelegramAdapter(socketio_server, start_maintenance=True)
    socketio_server.set_telegram_adapter(adapter)

    try:
        await socketio_server.start()
        await adapter.start()
        while adapter.running:
            await asyncio.sleep(5)
    except (ValueError, FileNotFoundError) as e:
        logging.error(f"Configuration error: {e}")
        logging.error("Please ensure telegram_config.yaml exists with required settings")
    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        if adapter.running:
            await adapter.stop()
        await socketio_server.stop()

if __name__ == "__main__":
    asyncio.run(main())
