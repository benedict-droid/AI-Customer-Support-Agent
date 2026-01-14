from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.main import app_router
from core.logging import setup_logging
import logging

from mcp_integration.client import MCPClient

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Application startup: Logging initialized")
    
    # Initialize Shopware MCP Client
    shopware_client = MCPClient("http://localhost:3333/sse")
    await shopware_client.connect()
    
    # Store in a list for multi-client support
    app.state.mcp_clients = [shopware_client]
    
    yield
    
    # Disconnect all clients
    for client in app.state.mcp_clients:
        await client.disconnect()

    logger.info("Application shutdown")

app = FastAPI(title="AI Customer Support Agent", lifespan=lifespan)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allowing all for flexibility, or specify ["http://localhost:5173", "http://localhost:5174"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(app_router)
