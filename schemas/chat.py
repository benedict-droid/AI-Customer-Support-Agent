from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's query or input message.", example="Find me a red t-shirt")
    swAccessKey: str | None = Field(None, description="Shopware Sales Channel Access Key.", example="SWJAVW8YDRJ5RJN2D3I2WJ5WGA")
    swContextToken: str | None = Field(None, description="Shopware Context Token (Session/Cart ID).", example="a1b2c3d4e5f6...")
    swLanguageId: str | None = Field(None, description="Shopware Language ID for translation context.", example="2fbb5fe2e29a4d70aa5854ce7ce3e20b")
    shopUrl: str | None = Field(None, description="Base URL of the shop.", example="http://localhost:8000")
    pageContext: dict | None = Field(None, description="Current frontend state (e.g. active product).", example={"productId": "uuid...", "productName": "T-Shirt"})

class ChatResponse(BaseModel):
    message: str = Field(..., description="The AI's response message.")
    type: str = Field("text", description="Type of content: text, product_list, product_detail, cart_list, order_list.")
    suggestions: list[str] | None = Field(None, description="List of suggested follow-up questions.")
    data: list | dict | str | None = Field(None, description="Structured data payload corresponding to the type.")
    context: dict | None = Field(None, description="Updated context to be passed back in the next request.")
