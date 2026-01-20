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
                                last_tool_data = json.loads(function_response)
                            except:
                                last_tool_data = function_response

                        except Exception as e:
                            logger.error(f"Tool execution failed: {e}")
                            function_response = json.dumps({"error": str(e)})

                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                    })
                
                # Second API call with tool outputs (LLM now only provides message and type)
                second_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={ "type": "json_object" }
                )
                final_content = second_response.choices[0].message.content
            else:
                final_content = response_message.content
                last_tool_data = None

            # Attempt to parse as JSON and Stitch Data
            try:
                parsed_response = json.loads(final_content)
                # Ensure it has the required fields
                if not isinstance(parsed_response, dict) or "message" not in parsed_response:
                    return {
                        "message": final_content,
                        "type": "text",
                        "data": None
                    }
                
                # --- HYBRID STITCHING LOGIC ---
                # Automatically inject data if it's a structured response type
                if parsed_response.get("type") in ["product_list", "product_detail", "order_list"]:
                    parsed_response["data"] = last_tool_data
                else:
                    # For "text" or unknown types, ensure data is null or omitted
                    if "data" not in parsed_response:
                        parsed_response["data"] = None

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
