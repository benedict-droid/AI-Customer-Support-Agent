import os
from .base import BaseLLMClient
from .openai_client import OpenAIClient
from dotenv import load_dotenv

load_dotenv()


def get_llm_client(mcp_clients=None) -> BaseLLMClient:
    """
    Factory function to get the LLM client instance.
    For now, it defaults to OpenAIClient.
    """
    load_dotenv()
    # Simply return OpenAIClient for now as it's the only implementation
    return OpenAIClient(mcp_clients=mcp_clients)
