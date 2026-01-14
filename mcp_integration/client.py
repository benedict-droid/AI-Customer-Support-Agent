from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
import logging

logger = logging.getLogger(__name__)

class MCPClient:
    """
    Manages the connection to the Shopware MCP server via SSE.
    """
    def __init__(self, sse_url: str = "http://localhost:3333/sse"):
        self.sse_url = sse_url
        self.session: ClientSession | None = None
        self._exit_stack = None

    async def connect(self):
        """Establish connection to the MCP server."""
        try:
            from contextlib import AsyncExitStack
            self._exit_stack = AsyncExitStack()
            
            # Connect using sse_client context manager
            read_stream, write_stream = await self._exit_stack.enter_async_context(
                sse_client(self.sse_url, timeout=60.0)
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
