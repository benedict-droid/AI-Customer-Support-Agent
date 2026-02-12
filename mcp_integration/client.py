from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)

@dataclass
class StoreCredentials:
    shop_url: str
    client_id: str
    client_secret: str

class MCPClient:
    """
    Manages the connection to the Shopware MCP server via SSE.
    """
    def __init__(self, sse_url: str = "http://localhost:3334/sse"):
        self.sse_url = sse_url
        self.session: ClientSession | None = None
        self._exit_stack = None
        self.stores: Dict[str, StoreCredentials] = {}
        self.active_store_name: Optional[str] = None
        
        # Initialize default store from environment if available
        default_url = os.getenv("SHOPWARE_API_URL")
        default_id = os.getenv("SHOPWARE_API_CLIENT_ID")
        default_secret = os.getenv("SHOPWARE_API_CLIENT_SECRET")
        
        if default_url and default_id and default_secret:
            self.add_store("default", default_url, default_id, default_secret)
            self.set_active_store("default")

    def add_store(self, name: str, shop_url: str, client_id: str, client_secret: str):
        """Add a new store configuration."""
        self.stores[name] = StoreCredentials(shop_url, client_id, client_secret)
        logger.info(f"Added store '{name}'")

    def set_active_store(self, name: str):
        """Set the active store for subsequent tool calls."""
        if name not in self.stores:
            raise ValueError(f"Store '{name}' not found")
        self.active_store_name = name
        logger.info(f"Set active store to '{name}'")

    async def connect(self):
        """Establish connection to the MCP server."""
        try:
            from contextlib import AsyncExitStack
            self._exit_stack = AsyncExitStack()
            
            # Connect using sse_client context manager
            # timeout=5.0 sets connect/pool timeouts
            # sse_read_timeout=None disables the read timeout (infinite)
            read_stream, write_stream = await self._exit_stack.enter_async_context(
                sse_client(self.sse_url, timeout=5.0, sse_read_timeout=None)
            )
            
            # Start the session
            self.session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            
            await self.session.initialize()
            logger.info(f"Connected to MCP server at {self.sse_url}")
            
        except Exception as e:
            logger.error(f"Failed to connect to MCP server: {e}")
            await self.disconnect()
            raise

    async def disconnect(self):
        """Close the connection."""
        if self._exit_stack:
            await self._exit_stack.aclose()
            self._exit_stack = None
        self.session = None
        logger.info("Disconnected from MCP server")

    async def list_tools(self):
        """List available tools from the MCP server."""
        if not self.session:
            raise RuntimeError("MCP Client is not connected")
        
        result = await self.session.list_tools()
        return result.tools

    async def call_tool(self, name: str, arguments: dict):
        """Call a specific tool on the MCP server."""
        if not self.session:
            raise RuntimeError("MCP Client is not connected")
        
        # Inject active store credentials
        if self.active_store_name:
            creds = self.stores[self.active_store_name]
            arguments = arguments.copy() # Don't mutate original dict
            arguments["shop_url"] = creds.shop_url
            arguments["client_id"] = creds.client_id
            arguments["client_secret"] = creds.client_secret
        else:
             logger.warning("No active store set. Tool call might fail if credentials are required.")

        import time
        start_time = time.perf_counter()
        logger.info(f"Calling MCP tool '{name}' with args: {arguments}")
        
        try:
            result = await self.session.call_tool(name, arguments)
            duration = time.perf_counter() - start_time
            logger.info(f"MCP tool '{name}' executed in {duration:.3f}s")
            return result
        except Exception as e:
            duration = time.perf_counter() - start_time
            logger.error(f"MCP tool '{name}' failed after {duration:.3f}s: {e}")
            raise e
