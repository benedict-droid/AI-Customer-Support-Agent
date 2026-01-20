from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    swAccessKey: str | None = None
    swContextToken: str | None = None
    shopUrl: str | None = None

class ChatResponse(BaseModel):
    message: str
    type: str = "text"
    data: list | dict | None = None
    context: dict | None = None
