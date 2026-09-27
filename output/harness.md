# Campus Customs data harness

This document records the shape of `data/campus_customs.db` for the Campus Customs shop and merch chatbot. It is a working reference that we can extend as later homework tasks add behavior and tests.

## Database overview

The database contains four application tables:

| Table | Rows | Role |
|---|---:|---|
| `catalogue` | 102 | One row per product in the shop catalogue. |
| `inventory` | 612 | Size-level stock for catalogue products. |
| `users` | 3 | Customer accounts and password hashes. |
| `chat_messages` | 22 | Persisted chatbot conversation history and product results. |

The main relationship is `catalogue.product_id` → `inventory.product_id`. Both `users.id` and `chat_messages.user_id` are related, so each saved chat belongs to a customer account.

## `catalogue`

One row describes a sellable Yale merchandise item. This is the primary source for product cards, search, recommendations, product detail views, price answers, and image URLs.

| Field | Type / constraints | Why it matters |
|---|---|---|
| `product_id` | `TEXT PRIMARY KEY` | Stable identifier for product links, inventory joins, chatbot results, and UI selection. |
| `name` | `TEXT NOT NULL` | Customer-facing product name used in cards, search results, and chatbot responses. |
| `garment_type` | `TEXT NOT NULL` | Enables filters and natural-language matching such as hoodie, crewneck, jacket, or T-shirt. |
| `description` | `TEXT NOT NULL` | Gives the chatbot reliable details about design, construction, and intended style. |
| `colors` | `TEXT NOT NULL`; JSON array stored as text | Supports color filters and requests such as “show me navy and white options.” The application must JSON-decode it before using it as a list. |
| `search_tags` | `TEXT NOT NULL`; JSON array stored as text | Provides searchable concepts such as sport, college, graphic, and garment synonyms for product matching. |
| `image_file_path` | `TEXT NOT NULL` | Points to the supplied product image, for example `products/basic-hoodie-big-yale.jpg`; the frontend can turn this into a safe served-media URL. |
| `price` | `REAL NOT NULL` | The authoritative current price for product cards and chatbot price answers. |

## `inventory`

Each row represents the quantity of one catalogue product in one size. A product can therefore have multiple inventory rows.

| Field | Type / constraints | Why it matters |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Internal identifier for an inventory record; useful for administration and debugging, but not usually shown to shoppers. |
| `product_id` | `TEXT NOT NULL`, foreign key to `catalogue.product_id` | Connects size-specific stock to the product shoppers are viewing or asking about. |
| `size` | `TEXT NOT NULL` | The variant a shopper needs to select, such as XS, S, M, L, XL, or XXL. |
| `quantity` | `INTEGER NOT NULL` | Current units available for that product-size combination; drives “in stock,” “low stock,” and unavailable answers. |

The `(product_id, size)` pair is `UNIQUE`, so there should be at most one stock record per size for a product. The table currently has 612 rows for 102 catalogue products, which is an average of six size rows per product.

## `users`

Each row represents a customer account. The table supports account creation, recognizing a signed-in shopper, and associating conversations with a user.

| Field | Type / constraints | Why it matters |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Stable internal account identifier and the parent key used by `chat_messages.user_id`. |
| `name` | `TEXT NOT NULL` | Display name for account UI and a friendly chatbot experience. |
| `email` | `TEXT NOT NULL UNIQUE` | Login and account identity; uniqueness prevents duplicate accounts. |
| `password_hash` | `TEXT NOT NULL` | Stores a one-way password representation for authentication. The plaintext password must never be stored, logged, returned by an API, or placed in this harness. |
| `created_at` | `TEXT NOT NULL`, defaults to `datetime('now')` | Account creation timestamp for auditing and future customer/account features. |
| `first_name` | `TEXT` | Optional structured first name for personalization and account forms. |
| `last_name` | `TEXT` | Optional structured last name for personalization and future order or delivery details. |

`email` is the only declared uniqueness constraint. Authentication code should use a password-hashing library compatible with the database’s existing hash format and should avoid exposing user records unnecessarily.

## `chat_messages`

This table stores the conversation between a customer and the chatbot, including product results that were shown for a response.

| Field | Type / constraints | Why it matters |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Stable identifier for a single message and chronological debugging. |
| `user_id` | `INTEGER NOT NULL`, foreign key to `users.id` | Associates a message with the customer account whose conversation it belongs to. |
| `role` | `TEXT NOT NULL` | Distinguishes customer messages such as `user` from assistant messages such as `assistant`, so history can be reconstructed for the agent. |
| `content` | `TEXT NOT NULL` | The message text sent by the shopper or generated by the chatbot. This is the core conversation context. |
| `products_json` | `TEXT`, nullable JSON | Stores product recommendations/results displayed with an assistant response. It can keep the chat UI synchronized with what the customer saw; the application must JSON-decode it. |
| `created_at` | `TEXT NOT NULL`, defaults to `datetime('now')` | Provides ordering and timestamps for chat history, support debugging, and future analytics. |

## Implementation notes for later work

- Treat `catalogue` as the source of truth for names, descriptions, image paths, colors, tags, and prices.
- Join `inventory` by `product_id` and report availability by `size`; do not infer stock from product existence alone.
- Decode `colors`, `search_tags`, and `products_json` as JSON at the application boundary and validate malformed values gracefully.
- Keep image files and the SQLite database outside git, while retaining the schema and this harness as documentation.
- Never send `password_hash` values to the browser or the AI agent. The chatbot needs catalogue and inventory context, not credentials.
- Product recommendations returned by the agent should include stable `product_id` values so the page can reveal the matching products reliably.

## Authentication behavior

The account flow stores `first_name`, `last_name`, a combined display `name`, the normalized `email`, a protected `password_hash`, and the database-managed `id` and `created_at` values in `users`. The browser receives an opaque signed session token after registration or login; it does not receive the password or password hash.

New passwords are protected with salted `scrypt` hashes. The salt and cost parameters are stored alongside the derived digest so the server can verify a password without storing the original text. The seed test account (`test@campuscustoms.yale.edu`) uses the database's legacy PBKDF2-SHA256 format with 120,000 rounds, which the login verifier supports for development compatibility. New accounts use `scrypt` rather than the legacy format.

The create-account form requires first name, last name, email, a 12-character minimum password, and matching confirmation. Login requires only email and password. Duplicate emails return a conflict, while invalid credentials return the same generic error for both an unknown email and a wrong password.

## Frontend, FastAPI, and agent wiring

The React/Vite chat widget sends the shopper's message as JSON to `POST http://127.0.0.1:8000/api/chat`:

```json
{ "message": "Do you have a navy Yale hoodie in large?" }
```

FastAPI validates the request in `backend/main.py`, calls `run_chat`, and returns the structured `ChatReply` JSON. The frontend displays the `reply` and uses any returned `products` as stylist picks. Product browsing remains available through `GET /api/products` and product images through the `/images/` static route.

The agent is assembled in `backend/agent.py`. It loads `backend/prompts/prompt.md` as the system prompt, creates an OpenAI-compatible PydanticAI model using `PORTKEY_MODEL` and the Portkey base URL, and authenticates with `PORTKEY_API_KEY` from `.env`. The agent returns the `ChatReply` type from `backend/models.py` and can call `search_catalog`, `get_product_stock`, and `get_product_details` from `backend/tools.py`. If no Portkey key is configured, `/api/chat` returns a safe setup message instead of exposing a credential or crashing the catalog API.

Run the backend from the `backend` directory as required:

```powershell
cd hw-4/backend
uvicorn main:app --reload --port 8000
```

The frontend runs separately from `hw-4/frontend` with `npm run dev` and expects the API at `http://127.0.0.1:8000`. The CORS allowlist includes Vite's normal ports 5173 and 5174.

## Improvement layer

The Products page now supports catalogue search plus garment, color, sport/college, size-available, availability, maximum-price, and sort controls. Product cards show low-stock or out-of-stock badges, and loading skeletons keep the layout stable while the API responds.

The chat panel now has suggested questions, a disabled/loading state while a request is running, and save/view actions on dynamic result cards. Logged-in shoppers can save products to a user-scoped wishlist in browser storage; guest shoppers are sent to login when they try to save. The product detail view exposes the same save action.

Before invoking PydanticAI, `run_chat` uses `deterministic_answer` for unambiguous price and size-stock questions. Those responses are generated only from SQLite. LLM responses pass through `validate_reply`, which rejects unsupported currency values and explicit stock quantities; the API then returns a safe verification message while the structured product cards remain database-backed. More ambiguous styling and recommendation questions continue to use the agent.

The backend environment is `hw-4/.venv`, created from `requirements.txt`. On Windows, activate it from the project folder with `.venv\\Scripts\\Activate.ps1`, change into `backend`, and run the required Uvicorn command:

```powershell
cd hw-4
.venv\\Scripts\\Activate.ps1
cd backend
uvicorn main:app --reload --port 8000
```

## Pipeline audit record

The first end-to-end audit passed after installing Python 3.12.10 and creating `.venv`:

- `pip check`: no broken requirements.
- Backend imports successfully both as `backend.main` and as `main` from `backend/`.
- `GET /api/health`: 200; `GET /api/products`: 200 with 102 products.
- All 102 catalogue image paths resolve to files in `data/products`.
- Seed login succeeds for the development test user; wrong credentials return 401.
- A temporary new account was created and authenticated successfully; duplicate registration returns 409. The temporary record was removed after the test.
- A live Portkey/PydanticAI request returned a structured reply and product cards for a navy hoodie and size-M request.
- The frontend `npm run build` passes.

## Database lookup tools and return fields

The agent has three database-backed tools. Each opens `data/campus_customs.db` directly and closes the connection after the lookup.

### `search_catalog(query, limit)`

This is the discovery tool for natural-language requests such as “navy hoodie” or “Harvard-Yale shirt.” It searches the catalogue name, garment type, description, colors, and search tags, ranks matches by how many query words they contain, and then joins each result to `inventory`.

It returns `ProductCard` values with these fields:

| Field | Source | Why it is returned |
|---|---|---|
| `product_id` | `catalogue.product_id` | Stable identifier for the frontend card and for an exact stock lookup. |
| `name` | `catalogue.name` | The customer-facing product title. |
| `price` | `catalogue.price` | The authoritative database price; the model must not invent or recalculate it. |
| `garment_type` | `catalogue.garment_type` | Lets the agent explain whether the item is a hoodie, T-shirt, crewneck, and so on. |
| `description` | `catalogue.description` | Supplies the factual product copy used in recommendations. |
| `image_url` | Filename from `catalogue.image_file_path` | Lets the frontend display the same product the agent recommended. |
| `inventory` | `inventory.size`, `inventory.quantity` | Carries every size and its exact quantity, including zero quantities. |
| `total_stock` | Sum of `inventory.quantity` | Useful for a broad in-stock/out-of-stock summary, but never substitutes for a size-specific answer. |

Each `inventory` entry is a `SizeStock` model with `size`, `quantity`, and `in_stock`. `in_stock` is derived only from `quantity > 0`; it is not guessed by the agent.

### `get_product_stock(product_id)`

This is the exact lookup tool for a known product and is required for exact size, quantity, and availability questions. It returns `ProductStockLookup` with `product_id`, `name`, `description`, `price`, and an `inventory` list of `SizeStock` records. Returning the description and price here as well as from search makes an exact lookup self-contained and keeps the response tied to one catalogue row.

The prompt explicitly requires the agent to use these tools for every product fact. `run_chat` also performs an authoritative `search_catalog` lookup before the model is called and returns those database-backed product cards to the browser, so model-generated text cannot create fake price or quantity fields. A quantity of zero is represented as `in_stock: false` and must be stated clearly as “Out of stock.”

## Chat search results to product cards

The chat contract is:

```json
{
  "reply": "Here are several Yale hoodies currently in the catalogue.",
  "products": [
    {
      "product_id": "basic-hoodie-big-yale",
      "name": "Basic Hoodie Big Yale",
      "price": 68,
      "garment_type": "pullover hoodie",
      "description": "...",
      "colors": ["navy blue", "white"],
      "image_url": "/images/basic-hoodie-big-yale.jpg",
      "inventory": [{"size": "M", "quantity": 5, "in_stock": true}],
      "total_stock": 60
    }
  ]
}
```

The request starts in the floating React chat widget and is sent to `POST /api/chat` as `{ "message": "what hoodies do you have?" }`. FastAPI calls `run_chat`; `run_chat` queries SQLite, calls PydanticAI with the database context and tools, and returns the structured `ChatReply`. The widget stores `products` in `chatProducts` and renders a catalogue-match strip inside the chat panel with the database image, name, garment type, and price.

Each match card navigates to `#/product/<product_id>`. The existing detail view resolves that ID against the full catalogue and displays the large image, full description, price, colors, and size-level stock. The detail lookup also falls back to the chat result data while the full catalogue is loading, so a chat-inserted card retains the same single-item-page behavior as a normal Products-page card.
The example query `what hoodies do you have?` is normalized from plural `hoodies` to the catalogue's singular `hoodie` term, producing eight database-backed cards in the current catalogue. The card strip is intentionally inside the floating chat panel so the customer can compare the response and results together without losing the current page.

## Authenticated chat history and agent context

The browser sends `Authorization: Bearer <session token>` with chat requests when a customer is logged in. `POST /api/chat` accepts both guests and authenticated customers. For an authenticated request, FastAPI verifies the signed token, resolves the user from `users`, and inserts two rows into `chat_messages`: the shopper message with `role = "user"`, and the agent response with `role = "assistant"`. The assistant row stores its structured product-card array in `products_json`, so the UI can restore both text and catalogue matches. Guests receive the same live response but no `chat_messages` rows are written.

Logged-in history is loaded with `GET /api/chat/history`. On app startup and after a successful login, the frontend fetches that route, maps each row's `content` into the chat transcript, and restores the most recent saved `products` array into the result-card strip. History is scoped by the verified token's user ID; the browser never chooses a user ID directly.

The agent receives an `AgentDeps` object on every run. It contains `CustomerContext` (`user_id`, `name`, and `email`) when logged in, or an empty guest context, plus optional `PageContext` containing the current `product_id`. The frontend sends that page context with chat requests when the shopper is on a product detail route. The backend resolves the ID against SQLite before the model runs and adds the canonical product to the verified context. A dynamic PydanticAI system-prompt function makes the shopper identity and current product context available to the agent without putting secrets in the user message. The agent can also call `get_product_details` or `get_product_stock` to verify the current item.

## Final system specification

### Models and fields

The Pydantic models in `backend/models.py` are the typed contract between SQLite-backed tools, PydanticAI, FastAPI, and React:

| Model | Fields | Why these fields were chosen |
|---|---|---|
| `CustomerContext` | `user_id`, `name`, `email` | Gives the agent minimal identity context for personalization and ownership without exposing passwords or hashes. All fields are optional so guests work naturally. |
| `PageContext` | `product_id` | Carries the product currently open in the browser, allowing “this hoodie” questions to resolve to one canonical catalogue row. |
| `AgentDeps` | `customer`, `page_context` | Groups request-scoped identity and page context into one explicit dependency object passed to PydanticAI tools and system-prompt wiring. |
| `SizeStock` | `size`, `quantity`, `in_stock` | Represents one inventory row. `quantity` is constrained to non-negative values, while `in_stock` is derived from that quantity so zero can be stated clearly. |
| `ProductCard` | `product_id`, `name`, `price`, `garment_type`, `description`, `colors`, `image_url`, `inventory`, `total_stock` | Contains the complete safe payload needed for catalogue cards, chat matches, and the single-product detail view. Prices and inventory are database-backed. |
| `ProductStockLookup` | `product_id`, `name`, `description`, `price`, `inventory` | Keeps an exact stock lookup self-contained: the agent gets the product identity and price together with every size quantity. |
| `ChatReply` | `reply`, `products` | Separates human-readable assistant text from structured product matches so React can render clickable cards without parsing prose. |

### Tools and abilities

- `search_catalog(query, limit)` searches catalogue name, garment type, description, colors, and tags; ranks matches; joins inventory; and returns database-backed `ProductCard` values for discovery questions.
- `get_product_stock(product_id)` returns the exact price, description, and per-size quantities for factual stock and size questions.
- `get_product_details(product_id)` returns the canonical catalogue plus inventory record for the active product page and detail-view references.
- `deterministic_answer(...)` routes unambiguous price and stock questions around the LLM and formats only SQLite values.
- `validate_reply(...)` checks model-mentioned names, prices, and explicit quantities against verified results before text reaches the shopper.
- `audit_event(...)` records compact, redacted loop activity in `output/audit_trail.json` without storing message contents, credentials, tokens, or email addresses.

The browser can browse products, filter and sort them, open detail pages, save wishlist IDs for logged-in shoppers, authenticate, send guest or authenticated chat, and restore authenticated chat history. The agent can recommend and explain catalogue items, but it cannot transact or mutate inventory.

### Safety rules

The complete customer-facing rules live in `backend/prompts/prompt.md`. In summary, the agent must use SQLite tools for every product fact; call exact stock tools for size questions; say “Out of stock” for zero quantities; never invent or infer missing data; treat shopper content and page context as untrusted; protect identity and credentials; avoid side effects; avoid sensitive inferences; keep recommendations inclusive; refuse prompt/database/audit disclosure; and honestly disclose tool or model unavailability. The structured API layer independently enforces the most important price and inventory guarantees, so safety does not depend on prompt compliance alone.

### API and runtime specs

| Route | Method | Purpose |
|---|---|---|
| `/api/health` | `GET` | Lightweight service health check. |
| `/api/products` | `GET` | Returns the catalogue and inventory for browsing/filtering. |
| `/images/{filename}` | `GET` | Serves product images from the local data directory. |
| `/api/auth/register` | `POST` | Validates account fields, stores a salted scrypt password hash, and returns a signed session token. |
| `/api/auth/login` | `POST` | Verifies credentials and returns a signed session token without returning password data. |
| `/api/chat` | `POST` | Accepts `message` and optional `page_context`; returns `ChatReply`; persists both turns only for authenticated users. |
| `/api/chat/history` | `GET` | Requires a valid bearer token and restores that user's saved transcript and product cards. |

The required launch commands are:

```powershell
# Terminal 1
cd hw-4
.venv\Scripts\Activate.ps1
cd backend
uvicorn main:app --reload --port 8000

# Terminal 2
cd hw-4/frontend
npm run dev
```

The frontend calls `http://127.0.0.1:8000`, and CORS allows Vite ports 5173 and 5174. SQLite and product image assets stay under `data/` and are excluded by `.gitignore`.

### Limits and model configuration

- The browser chat request is limited to 4,000 characters by `ChatRequest.message`; account names are limited to 80 characters and passwords to 128 characters.
- `run_chat` caps verified product cards at 8 per response. `search_catalog` also clamps every tool-requested limit to 1–8, so a model cannot cause an unbounded catalogue result set.
- Each HTTP chat request makes one application-level agent run. The PydanticAI agent is configured with `retries=2`, allowing at most two validation/tool retry attempts before the request fails into the safe fallback path; there is no open-ended application loop.
- The configured model is `PORTKEY_MODEL` from the workspace `.env`, defaulting to `gpt-5.6-luna`, accessed through Portkey's OpenAI-compatible base URL. `PORTKEY_API_KEY` is loaded from `.env` and never placed in source code or responses.
- Product facts are always preloaded from SQLite before the model run. Simple price/stock questions bypass the model entirely; ambiguous recommendations use the bounded PydanticAI run.

The latest grading audit also verified `GET /api/health` (200), 102 catalogue products, product detail and image delivery, CORS from the active Vite port, seed login, unauthorized history protection, generic wrong-password rejection, deterministic medium-stock output, eight hoodie result cards, valid audit JSON, backend compilation, `pip check`, and the frontend production build.

### Append-only audit trail

`output/audit_trail.json` is initialized as a JSON array and is never reset by the application. Each agent-loop event appends an object with:

```json
{
  "time": "UTC ISO-8601 timestamp",
  "tool_name": "search_catalog",
  "arguments": {"query_preview": "hoodies", "limit": 8},
  "stop_reason": "returned_8_matches"
}
```

Database tools log successful lookups; the loop logs deterministic answers, missing-key stops, validated model replies, and external-model fallbacks. Logging is best-effort and thread-locked so an audit-file problem cannot break shopping. Arguments are short and redacted by design.
