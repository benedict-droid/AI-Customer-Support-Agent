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
    print(f"\n[DEBUG] INCOMING REQUEST: {request.message}")
    print(f"[DEBUG] Full PageContext: {request.pageContext}")
    logger.info(f"Received chat message: {request.message}")
    
    # 1. Identify Session
    session_id = request.swContextToken
    if not session_id:
        logger.warning("No swContextToken provided. Using 'anonymous' session.")
        session_id = "anonymous"
    
    # 2. Initialize Session if new (dictionary structure)
    if session_id not in sessions:
        sessions[session_id] = {"history": [], "context": {"active_product": None}}
    
    # Migration for old list-based sessions (development helper)
    if isinstance(sessions[session_id], list):
        sessions[session_id] = {"history": sessions[session_id], "context": {"active_product": None}}
    
    # 3. Add User Message
    sessions[session_id]["history"].append({"role": "user", "content": request.message})
    
    # 3.5. Handle Frontend Context (Page Tracking)
    if request.pageContext is not None:
        p_id = request.pageContext.get("productId")
        if p_id:
            # User is on a product page
            p_name = request.pageContext.get("productName") or "Current Product"
            sessions[session_id]["context"]["active_product"] = {
                "id": p_id,
                "name": p_name
            }
            logger.info(f"Frontend Context Set Active: {p_id} ({p_name})")
        else:
            # User is NOT on a product page (e.g. Home, Category) -> Clear context
            sessions[session_id]["context"]["active_product"] = None
            logger.info("Frontend Context Cleared Active Product (Navigated away)")
    
    try:
        mcp_clients = getattr(req.app.state, "mcp_clients", [])
        client = get_llm_client(mcp_clients=mcp_clients)
        
        # 4. Get History for THIS session
        history_window = sessions[session_id]["history"][-HISTORY_LIMIT:]
        
        # Prepare conversion history (excluding current msg)
        conversation_history = history_window[:-1]
        
        # INJECT ACTIVE CONTEXT
        active_product = sessions[session_id]["context"].get("active_product")
        if active_product:
            # Check if we have the full details (description), if not, try to fetch them
            # This is critical for "landing page" questions where the user hasn't browsed yet
            product_context_desc = ""
            
            # Simple in-memory cache check or just fetch if we have ID
            # In a real app we'd cache this, but for now we fetch to be accurate
            if active_product.get('id') and not active_product.get('description'):
                try:
                    # We need to fetch details to answer questions like "is it waterproof"
                    # We use the generic generic_search or product_detail tool logic here
                    # For simplicity, we'll try to use the client directly if possible or just warn the LLM
                    # A better way is to tell LLM: "User is on Product X. YOU MUST CALL store_product_detail(id=X) to answer specific questions."
                    pass
                except Exception as e:
                    logger.error(f"Failed to auto-fetch context details: {e}")

            context_msg = (
                f"SYSTEM NOTE: User is currently viewing product '{active_product['name']}' "
                f"(ID: {active_product['id']}). "
                f"IMPORTANT: You have NOT loaded the full details for this product yet. "
                f"If the user asks specific questions like 'is it waterproof?' or 'features', "
                f"you MUST call the `store_product_detail` tool with ID '{active_product['id']}' "
                f"to retrieve the description and specs before answering."
            )
            # Insert at the beginning of history so it's treated as background context
            conversation_history.insert(0, {"role": "system", "content": context_msg})
            logger.info(f"Injected Active Context: {active_product['name']}")
        
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
        
        response_data = await client.generate_response(request.message, conversation_history=conversation_history, context=context)
        
        # Add assistant message to history with a data summary if present
        assistant_content = response_data.get("message", "")
        
        # UPDATE STATE (Active Context)
        resp_type = response_data.get("type")
        
        if resp_type == "product_detail" and response_data.get("data"):
            # SET Active Product
            p_data = response_data["data"]
            sessions[session_id]["context"]["active_product"] = {
                "id": p_data.get("id"),
                "name": p_data.get("name")
            }
            logger.info(f"Set Active Product: {p_data.get('name')}")
            
        elif resp_type in ["product_list", "order_list", "cart_list"]:
            # CLEAR Active Product on list views
            sessions[session_id]["context"]["active_product"] = None
            logger.info("Cleared Active Product Context")

        if response_data.get("data"):
            data = response_data["data"]
            if isinstance(data, dict) and "results" in data:
                # Summarize list (ID and Name)
                summary = " | ".join([f"{r.get('name')} (ID: {r.get('id')})" for r in data["results"][:3]])
                assistant_content += f"\n[Displayed: {summary}]"
            elif isinstance(data, dict) and "id" in data:
                # Single item - include description in history for context
                desc = data.get('description', '') or ''
                # Truncate description to save context tokens, but keep enough for Q&A
                desc_preview = (desc[:2000] + '...') if len(desc) > 2000 else desc
                assistant_content += f"\n[Displayed: {data.get('name')} (ID: {data.get('id')})\nDescription: {desc_preview}]"
        
        # 5. Save Assistant Message to THIS session
        sessions[session_id]["history"].append({"role": "assistant", "content": assistant_content})

        logger.info(f"Assistant response: {assistant_content}")
        logger.debug(f"Session {session_id} history length: {len(sessions[session_id]['history'])}")
        
        return ChatResponse(
            message=response_data.get("message", ""),
            type=response_data.get("type", "text"),
            data=response_data.get("data"),
            suggestions=response_data.get("suggestions"),
            context={**context, **(response_data.get("context") or {})}
        )
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        return ChatResponse(response="Sorry, I encountered an error providing a response.")
