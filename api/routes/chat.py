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
        context = {
            "swAccessKey": request.swAccessKey,
            "swContextToken": request.swContextToken,
            "shopUrl": request.shopUrl
        }
        # Filter None values
        context = {k: v for k, v in context.items() if v is not None}
        
        response_data = await client.generate_response(request.message, conversation_history=history_window[:-1], context=context)
        
        # Add assistant message to history with a data summary if present
        # This helps the LLM remember IDs for follow-up questions (e.g., "Tell me more about the first jacket")
        assistant_content = response_data.get("message", "")
        if response_data.get("data"):
            data = response_data["data"]
            if isinstance(data, dict) and "results" in data:
                # Summarize list (ID and Name)
                summary = " | ".join([f"{r.get('name')} (ID: {r.get('id')})" for r in data["results"][:3]])
                assistant_content += f"\n[Displayed: {summary}]"
            elif isinstance(data, dict) and "id" in data:
                # Single item
                assistant_content += f"\n[Displayed: {data.get('name')} (ID: {data.get('id')})]"
        
        chat_history.append({"role": "assistant", "content": assistant_content})

        logger.info(f"Assistant response: {assistant_content}")
        logger.info(f"Conversation history: {chat_history}")
        
        return ChatResponse(
            message=response_data.get("message", ""),
            type=response_data.get("type", "text"),
            data=response_data.get("data"),
            context={**context, **(response_data.get("context") or {})}
        )
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        # Return a generic error message or raise HTTPException
        return ChatResponse(response="Sorry, I encountered an error providing a response.")
