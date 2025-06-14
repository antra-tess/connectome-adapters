import asyncio
import logging
import signal
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.adapters.telegram_adapter.adapter import Adapter
from src.core.rate_limiter.rate_limiter import RateLimiter
from src.core.utils.logger import setup_logging
from src.core.utils.config import Config
from src.core.socket_io.server import SocketIOServer

should_shutdown = False

def shutdown():
    """Perform graceful shutdown when signal is received"""
    global should_shutdown
    logging.warning("Shutdown signal received, initiating shutdown...")
    should_shutdown = True

async def main():
    try:
        config = Config("config/telegram_config.yaml")
        RateLimiter.get_instance(config)
        setup_logging(config)

        logging.info("Starting Telegram adapter")

        socketio_server = SocketIOServer(config)
        adapter = Adapter(config, socketio_server, start_maintenance=True)
        socketio_server.set_adapter(adapter)

        await socketio_server.start()
        await adapter.start()
        while adapter.running and not should_shutdown:
            await asyncio.sleep(1)
    except (ValueError, FileNotFoundError) as e:
        print(f"Configuration error: {e}")
        print("Please ensure telegram_config.yaml exists with required settings")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if adapter.running:
            await adapter.stop()
        await socketio_server.stop()

if __name__ == "__main__":
    asyncio.run(main())
