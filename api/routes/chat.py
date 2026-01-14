from fastapi import APIRouter, Request
from schemas.chat import ChatRequest, ChatResponse
import logging
import os

from llm.factory import get_llm_client

router = APIRouter()
logger = logging.getLogger(__name__)

# Simple in-memory history (global variable)
# In production, use Redis or a database per session_id
chat_history = []
HISTORY_LIMIT = int(os.getenv("CHAT_HISTORY_LIMIT", "6"))

@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request):
    logger.info(f"Received chat message: {request.message}")
    
    # Add user message to history
    chat_history.append({"role": "user", "content": request.message})
    
    try:
        mcp_clients = getattr(req.app.state, "mcp_clients", [])
        client = get_llm_client(mcp_clients=mcp_clients)
        
        # Get last N messages (window)
        history_window = chat_history[-HISTORY_LIMIT:]
        
        # Pass history to generate_response
        response_text = await client.generate_response(request.message, conversation_history=history_window[:-1])
        
        # Add assistant response to history
        chat_history.append({"role": "assistant", "content": response_text})
        
        return ChatResponse(response=response_text)
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        # Return a generic error message or raise HTTPException
        return ChatResponse(response="Sorry, I encountered an error providing a response.")
