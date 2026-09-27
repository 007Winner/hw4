# Campus Customs usability improvements

This write-up describes the four improvements added to Campus Customs and why they matter to a Yale merchandise shopper and to the shop team.

## Frontend improvement 1: better product discovery

The Products page now has a refinement panel with:

- garment type
- color
- sport or college affiliation
- size availability
- in-stock or out-of-stock status
- maximum price
- sorting by name or price

The catalogue also shows the number of matching pieces, low-stock badges, explicit out-of-stock badges, and loading skeletons while products are being retrieved.

This helps shoppers narrow a 102-item catalogue to something relevant quickly. A shopper looking for a navy Yale hoodie in medium can combine garment, color, and size filters instead of scanning every card. Price and stock controls also reduce frustration by hiding items that do not fit a shopper’s budget or availability needs. For the business, clearer discovery makes the catalogue easier to browse and makes inventory status visible before a customer opens a detail page.

## Frontend improvement 2: stronger shopping and chat UX

The floating stylist panel now includes:

- suggested starter questions
- a disabled input and “Checking the catalogue...” state while a request is running
- database-backed matching product cards
- visible price, garment type, and stock status on chat matches
- direct card navigation to the existing full product detail view
- save-to-wishlist actions on catalogue cards, chat cards, and product detail pages
- a “Saved only” catalogue filter

Wishlist data is scoped by the logged-in shopper’s email in browser storage. Guests are directed to log in before saving items. This gives shoppers an easy way to compare pieces, return to favorites, and move from an assistant recommendation to full product information without losing the shopping flow. Suggested prompts lower the barrier for first-time chat users, and loading feedback makes the live AI request feel intentional rather than broken.

## Backend improvement 1: deterministic product-answer validation

The backend now validates product facts before they reach the page. The `run_chat` pipeline:

1. Reads matching products and inventory directly from SQLite.
2. Answers unambiguous price and size-stock questions without calling the language model.
3. Validates model-generated product names, currency values, and explicit stock quantities against the verified database results.
4. Returns a safe verification message if a model claim cannot be validated.
5. Always returns database-backed structured product cards rather than trusting model-created price or quantity fields.

This protects the shopper from an invented price or availability claim and protects the business from displaying incorrect inventory. Size questions such as “Is medium in stock?” use the exact `M` inventory row, and zero quantity is clearly reported as “Out of stock.”

## Backend improvement 2: database-first routing for simple questions

Questions that clearly ask for a product price or exact stock are routed to deterministic Python/database logic. For example:

- “What is the price of this hoodie?” returns the catalogue price directly.
- “Is medium in stock?” looks up the exact `M` inventory row.
- “Is large available?” reports the exact quantity or clearly says “Out of stock.”

Styling, discovery, and ambiguous recommendation questions still use the PydanticAI agent and its catalogue tools. This split improves reliability, lowers latency, and avoids spending an AI request on a fact that SQLite can answer exactly.

## Runtime verification

The implementation was checked with:

- FastAPI health and product endpoints
- live product catalogue loading
- frontend Vite production build
- deterministic price and size-stock requests
- an out-of-stock request
- product-name and price validation tests
- the live chat contract and structured product-card response

The live recommendation check for “What hoodies do you have?” returned eight
SQLite-backed cards. When the external model endpoint was unavailable, the
API still returned those cards with a clear temporary-unavailability message;
the shopper can continue to inspect verified prices and size stock.

The app should be run with the backend from `hw-4/backend`:

```powershell
cd hw-4
.venv\\Scripts\\Activate.ps1
cd backend
uvicorn main:app --reload --port 8000
```

In a second terminal, run the frontend:

```powershell
cd hw-4/frontend
npm run dev
```

Then open the Vite URL, select Products, try the filters, open the stylist, use a suggested question, and click a returned product card to verify the full detail view.
