from abc import ABC, abstractmethod

class BaseLLMClient(ABC):
    @abstractmethod
    async def generate_response(self, message: str, conversation_history: list = None, context: dict = None) -> str:
        """
        Generate a response from the LLM based on the message and history.
        """
        raise NotImplementedError
