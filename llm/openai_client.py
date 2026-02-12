from .base import BaseLLMClient
from openai import OpenAI
import os
import logging
import json
from llm.prompts import SYSTEM_PROMPT
from mcp_integration.client import MCPClient

logger = logging.getLogger(__name__)

class OpenAIClient(BaseLLMClient):
    def __init__(self, mcp_clients: list[MCPClient] = None):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.error("OPENAI_API_KEY is missing from environment variables")
            raise ValueError("OPENAI_API_KEY is not set in environment variables.")
        
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        logger.info(f"Initializing OpenAIClient with model: {self.model}")
        self.client = OpenAI(api_key=api_key)
        self.mcp_clients = mcp_clients or []

    async def generate_response(self, message: str, conversation_history: list = None, context: dict = None) -> dict:
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            if conversation_history:
                messages.extend(conversation_history)
            messages.append({"role": "user", "content": message})

            tools = []
            tool_to_client_map = {}

            # Fetch tools from all clients
            for client in self.mcp_clients:
                if client.session:
                    try:
                        mcp_tools = await client.list_tools()
                        for tool in mcp_tools:
                            tools.append({
                                "type": "function",
                                "function": {
                                    "name": tool.name,
                                    "description": tool.description,
                                    "parameters": tool.inputSchema
                                }
                            })
                            tool_to_client_map[tool.name] = client
                    except Exception as e:
                        logger.error(f"Failed to list tools from client {client}: {repr(e)}")

            logger.info(f"Sending request to OpenAI with {len(tools)} tools")
            
            # First API call
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
            )
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            if tool_calls:
                messages.append(response_message)
                last_tool_data = None
                
                # Store results for all tools
                tool_results_map = {}
                
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"Executing tool: {function_name}")
                    
                    client = tool_to_client_map.get(function_name)
                    if not client:
                         function_response = json.dumps({"error": f"Tool {function_name} not found"})
                    else:
                        try:
                            if context:
                                function_args.update(context)
                            tool_result = await client.call_tool(function_name, function_args)
                            # Correctly extract text from tool result content
                            function_response = ""
                            if hasattr(tool_result, 'content'):
                                for content in tool_result.content:
                                    if hasattr(content, 'text'):
                                        function_response += content.text
                                    elif isinstance(content, dict) and 'text' in content:
                                        function_response += content['text']
                                    else:
                                        function_response += str(content)
                            else:
                                function_response = str(tool_result)
                            
                            # Capture tool data for stitching (attempt to parse JSON)
                            try:
                                parsed_tool_data = json.loads(function_response)
                                tool_results_map[function_name] = parsed_tool_data
                            except:
                                tool_results_map[function_name] = function_response

                        except Exception as e:
                            logger.error(f"Tool execution failed: {e}")
                            function_response = json.dumps({"error": str(e)})

                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                    })
                
                # --- CROSS-SELLING INTERCEPTOR ---
                if "store_cart_add" in tool_results_map:
                    try:
                        search_tool = "store_product_search"
                        search_client = tool_to_client_map.get(search_tool)
                        
                        # 1. Get Product ID from Cart Add
                        added_product_id = None
                        for tool_call in tool_calls:
                            if tool_call.function.name == "store_cart_add":
                                args = json.loads(tool_call.function.arguments)
                                added_product_id = args.get("productId")
                                break
                        
                        if added_product_id and search_client:
                            # 2. Fetch Product Details (Internal Tool Call) to get Category
                            detail_tool = "store_product_detail"
                            detail_client = tool_to_client_map.get(detail_tool)
                            
                            category_name = None
                            
                            if detail_client:
                                try:
                                    logger.info(f"Fetching details for product {added_product_id} to find category...")
                                    detail_args = {"productId": added_product_id}
                                    if context: detail_args.update(context)
                                    
                                    detail_result = await detail_client.call_tool(detail_tool, detail_args)
                                    # Extract JSON from detail result
                                    detail_json_str = ""
                                    if hasattr(detail_result, 'content'):
                                        for content in detail_result.content:
                                            if hasattr(content, 'text'):
                                                detail_json_str += content.text
                                    else:
                                        detail_json_str = str(detail_result)
                                        
                                    try:
                                        product_details = json.loads(detail_json_str)
                                        category_name = product_details.get("categoryName")
                                        if not category_name and product_details.get("name"):
                                             # Fallback to name if category missing, but user specifically asked for category logic.
                                             # User said "if the add to cart have category then only... else no need to show"
                                             # So we should be strict.
                                             pass
                                    except:
                                        pass
                                except Exception as e:
                                    logger.error(f"Failed to fetch product details for cross-sell: {e}")

                            # 3. Conditional Search
                            if category_name:
                                search_term = f"{category_name} accessories or related products"
                                logger.info(f"Cross-Sell: Found category '{category_name}'. Searching for: {search_term}")
                                
                                search_args = {"term": search_term}
                                if context: search_args.update(context)
                                
                                # Execute the tool directly
                                tool_result = await search_client.call_tool(search_tool, search_args)
                            
                            # Extract content
                            cs_response = ""
                            if hasattr(tool_result, 'content'):
                                for content in tool_result.content:
                                    if hasattr(content, 'text'):
                                        cs_response += content.text
                                    elif isinstance(content, dict) and 'text' in content:
                                        cs_response += content['text']
                                    else:
                                        cs_response += str(content)
                            else:
                                cs_response = str(tool_result)
                            
                            # Conditional Check: Only inject if results found
                            # We look for "total": 0 or explicit empty list if parsed, or heuristic string check
                            has_results = True
                            if '"total": 0' in cs_response or '"total":0' in cs_response:
                                has_results = False
                            
                            if has_results:
                                # 3. Add to results map so Stitching Logic sees it (and sets type=product_list)
                                try:
                                    parsed_cs = json.loads(cs_response)
                                    tool_results_map[search_tool] = parsed_cs
                                    
                                    # 4. Inject System Instruction for the LLM's text generation
                                    messages.append({
                                        "role": "system", 
                                        "content": f"SYSTEM AUTO-ACTION: Cart Add Successful. I performed a background search for '{search_term}'. Found: {cs_response}. Please recommend these items to the user in your response and ensure the response type is 'product_list'."
                                    })
                                except:
                                    pass
                    except Exception as e:
                        logger.error(f"Cross-selling interceptor failed: {e}")
                # Second API call with tool outputs (LLM now only provides message and type)
                second_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={ "type": "json_object" }
                )
                final_content = second_response.choices[0].message.content
            else:
                final_content = response_message.content
                tool_results_map = {}

            # Attempt to parse as JSON and Stitch Data
            try:
                logger.info(f"Raw LLM Content: {final_content}")
                parsed_response = json.loads(final_content)
                # Ensure it has the required fields
                if not isinstance(parsed_response, dict) or "message" not in parsed_response:
                    return {
                        "message": final_content,
                        "type": "text",
                        "data": None
                    }
                
                # --- HYBRID STITCHING LOGIC ---
                resp_type = parsed_response.get("type")
                
                # Map response types to expected tool sources
                type_to_tool = {
                    "product_list": "store_product_search",
                    "product_detail": "store_product_detail",
                    "cart_list": "store_cart_get",
                    "order_list": "store_order_list" # Assuming this tool exists
                }
                
                if resp_type in type_to_tool:
                    # Try to get data from the specific tool if it was called
                    target_tool = type_to_tool[resp_type]
                    if target_tool in tool_results_map:
                        parsed_response["data"] = tool_results_map[target_tool]
                    elif len(tool_results_map) > 0:
                        # Fallback: if specific tool missing but others exist, use the most recent one? 
                        # Or better, just grab the first one that looks like a match?
                        # For now, let's just grab values()[0] if single tool, or leave None to avoid mismatch
                        # Actually, looking at previous logic, it just took 'last_tool_data'.
                        # Let's try to be smart:
                         parsed_response["data"] = list(tool_results_map.values())[-1]
                    else:
                        parsed_response["data"] = None
                else:
                    # For "text" or unknown types, ensure data is null or omitted
                    if "data" not in parsed_response:
                        parsed_response["data"] = None
                
                # Ensure suggestions is None if missing
                if "suggestions" not in parsed_response:
                    parsed_response["suggestions"] = None

                return parsed_response

            except json.JSONDecodeError:
                return {
                    "message": final_content,
                    "type": "text",
                    "data": None
                }

        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            raise e
