from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.main import app_router
from core.logging import setup_logging
import logging

from mcp_integration.client import MCPClient
from dotenv import load_dotenv
import os

# Load env vars
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Application startup: Logging initialized")
    
    # Initialize Shopware Store MCP Client (Storefront)
    mcp_url = os.getenv("MCP_SERVER_URL", "http://localhost:3334/sse")
    shopware_store_client = MCPClient(mcp_url)
    try:
        await shopware_store_client.connect()
    except Exception as e:
        logger.error(f"Failed to connect to Shopware Store MCP: {e}")
    # logger.info("Skipping Shopware Store MCP connection for debugging")
    
    # Store in a list for multi-client support
    app.state.mcp_clients = [shopware_store_client]
    
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
