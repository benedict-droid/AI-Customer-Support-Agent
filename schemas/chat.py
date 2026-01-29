from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    swAccessKey: str | None = None
    swContextToken: str | None = None
    shopUrl: str | None = None
    pageContext: dict | None = None

class ChatResponse(BaseModel):
    message: str
    type: str = "text"
    suggestions: list[str] | None = None
    data: list | dict | str | None = None
    context: dict | None = None
