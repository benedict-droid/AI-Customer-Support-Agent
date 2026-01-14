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

    async def generate_response(self, message: str, conversation_history: list = None) -> str:
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
                        import traceback
                        logger.error(traceback.format_exc())

            logger.info(f"Sending request to OpenAI with {len(tools)} tools")
            
            import time
            start_time = time.perf_counter()

            # First API call
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
            )
            
            duration = time.perf_counter() - start_time
            logger.info(f"OpenAI initial response received in {duration:.3f}s")
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            if tool_calls:
                messages.append(response_message)
                
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"Executing tool: {function_name} with args: {function_args}")
                    
                    client = tool_to_client_map.get(function_name)
                    if not client:
                         logger.error(f"No client found for tool: {function_name}")
                         function_response = json.dumps({"error": f"Tool {function_name} not found"})
                    else:
                        try:
                            tool_result = await client.call_tool(function_name, function_args)
                            function_response = str(tool_result.content)
                            logger.info(f"Tool {function_name} result: {function_response}")
                            
                        except Exception as e:
                            logger.error(f"Tool execution failed: {e}")
                            function_response = json.dumps({"error": str(e)})

                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                    })
                
                # Second API call with tool outputs
                start_time_2 = time.perf_counter()
                second_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages
                )
                duration_2 = time.perf_counter() - start_time_2
                logger.info(f"OpenAI final response received in {duration_2:.3f}s")

                return second_response.choices[0].message.content
            
            return response_message.content

        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            raise e
