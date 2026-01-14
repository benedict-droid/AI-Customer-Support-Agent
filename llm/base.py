from abc import ABC, abstractmethod

class BaseLLMClient(ABC):
    @abstractmethod
    async def generate_response(self, message: str, tools: list = None) -> str:
        """Generate a response from the LLM based on the input message."""
        pass
