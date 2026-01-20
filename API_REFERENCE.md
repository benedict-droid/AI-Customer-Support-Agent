# API Reference: AI Customer Support Agent

## Base URL
`http://localhost:8000`

## Endpoints

### 1. Chat with Agent
**URL**: `/chat`
**Method**: `POST`
**Description**: Sends a message to the AI agent and receives a structured response.

#### Request Body
```json
{
  "message": "Show me red jackets",
  "swAccessKey": "SWSCAVBKV3VZOTFHUUR1QTJKUW",
  "swContextToken": "OPTIONAL_CONTEXT_TOKEN",
  "shopUrl": "https://shopware67demo.buildsite.in"
}
```
*   `message` (string, required): The user's input message.
*   `swAccessKey` (string, required): The Shopware Sales Channel Access Key.
*   `swContextToken` (string, optional): The session/context token for the current user (used for cart/session persistence).
*   `shopUrl` (string, optional): The base URL of the Shopware shop.

#### Response Body
The response is a structured JSON object designed for "Hybrid Stitching" - blending text with structured data.

```json
{
  "message": "I found these red jackets for you!",
  "type": "product_list", 
  "data": {
    "results": [
      {
        "id": "uuid...",
        "name": "Red Winter Jacket",
        "price": 199.99,
        "imageUrl": "https://...",
        "url": "https://...",
        "options": []
      }
    ],
    "pagination": { ... }
  },
  "context": {
    "swAccessKey": "...",
    "shopUrl": "..."
  }
}
```

#### Response Types (`type`)
The frontend should switch UI components based on the `type` field:

| Type | Description | Data Structure |
| :--- | :--- | :--- |
| `text` | Standard text response. | `null` |
| `product_list` | A list of products found by the agent. | `{ "results": [ProductObject] }` |
| `product_detail`| Detailed view of a single product. | `{ ProductObject }` |
| `order_list` | A list of user orders. | `{ "orders": [OrderObject] }` |

---

## Available Tools (MCP)

The Agent uses the following tools to interact with the Shopware Store API:

### Product Tools
*   `store_product_search`: Search for products by keyword.
*   `store_product_detail`: Get full details (description, properties) for a specific product ID.

### Cart Tools
*   `store_cart_get`: Retrieve the current contents of the cart.
*   `store_cart_add`: Add a product to the cart.
    *   Requires `productId` (UUID) and `quantity`.

### Order Tools
*   `store_order_list`: List recent orders for the authenticated customer.
*   `store_order_detail`: Get details of a specific order.

### Category Tools
*   `store_category_list`: List available categories.

### System Tools
*   `store_get_context`: Get the current context (currency, language, etc.).
