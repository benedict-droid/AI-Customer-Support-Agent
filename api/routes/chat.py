from fastapi import APIRouter, Request
from schemas.chat import ChatRequest, ChatResponse
import logging
import os

from llm.factory import get_llm_client

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory session storage (Dictionary)
# Key: swContextToken, Value: List of messages
# In production, use Redis with TTL
sessions = {}
HISTORY_LIMIT = int(os.getenv("CHAT_HISTORY_LIMIT", "6"))

@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request):
    logger.info(f"Received chat message: {request.message}")
    
    # 1. Identify Session
    session_id = request.swContextToken
    if not session_id:
        logger.warning("No swContextToken provided. Using 'anonymous' session.")
        session_id = "anonymous"
    
    # 2. Initialize Session if new
    if session_id not in sessions:
        sessions[session_id] = []
    
    # 3. Add User Message
    sessions[session_id].append({"role": "user", "content": request.message})
    
    try:
        mcp_clients = getattr(req.app.state, "mcp_clients", [])
        client = get_llm_client(mcp_clients=mcp_clients)
        
        # 4. Get History for THIS session
        history_window = sessions[session_id][-HISTORY_LIMIT:]
        
        # Pass history to generate_response
        context = {
            "swAccessKey": request.swAccessKey,
            "swContextToken": request.swContextToken,
            "shopUrl": request.shopUrl
        }
        # Filter None values
        context = {k: v for k, v in context.items() if v is not None}
        
        # Note: We pass the history window excluding the just-added user message if the LLM client adds it internally, 
        # but here we pass history_window[:-1] assuming generate_response takes history BEFORE current message
        # OR if generate_response handles the current message separately.
        # Based on previous code: conversation_history=history_window[:-1]
        
        response_data = await client.generate_response(request.message, conversation_history=history_window[:-1], context=context)
        
        # Add assistant message to history with a data summary if present
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
        
        # 5. Save Assistant Message to THIS session
        sessions[session_id].append({"role": "assistant", "content": assistant_content})

        logger.info(f"Assistant response: {assistant_content}")
        logger.debug(f"Session {session_id} history length: {len(sessions[session_id])}")
        
        return ChatResponse(
            message=response_data.get("message", ""),
            type=response_data.get("type", "text"),
            data=response_data.get("data"),
            context={**context, **(response_data.get("context") or {})}
        )
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        return ChatResponse(response="Sorry, I encountered an error providing a response.")
