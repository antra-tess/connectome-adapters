import asyncio
import logging
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from adapters.zulip_adapter.adapter.adapter import ZulipAdapter
from core.utils.logger import setup_logging
from core.utils.config import Config
from core.socket_io.server import SocketIOServer

async def main():
    try:
        config = Config("adapters/zulip_adapter/config/zulip_config.yaml")
        setup_logging(config)

        logging.info("Starting Zulip adapter")

        socketio_server = SocketIOServer(config)
        adapter = ZulipAdapter(
            config,
            socketio_server,
            start_maintenance=True
        )
        socketio_server.set_adapter(adapter)

        await socketio_server.start()
        await adapter.start()
        while adapter.running:
            await asyncio.sleep(5)
    except (ValueError, FileNotFoundError) as e:
        print(f"Configuration error: {e}")
        print("Please ensure zulip_config.yaml exists with required settings")
    except Exception as e:
        print(f"Unexpected error: {e}", exc_info=True)
    finally:
        if adapter.running:
            await adapter.stop()
        await socketio_server.stop()

if __name__ == "__main__":
    asyncio.run(main())
