# AI Prompts

This file records the prompts used for each problem section.

## Problem 2 — Analyze the database

let's take a look at the database data/campus\_customs.db and understand the fields of all the tables. It is important for us to know what's going on with the catalogue, inventory, and users fields in particular. Start a new file in the hw-4 folder called output/harness.md. Write down each table and its fields and a short line on why each field matters to us for the shop and/or chatbot that we are going to make. We are going to keep groing the harness file in later problems.

## Problem 3 — Build the Campus Customs Website

Okay. Now, you need to scaffold a react + vite + typescript front end for the campus customs website we're going to make. Put a navigation bar at the top that links to five main pages:

home
products
about us
log in
create account

Use similar wording to what you can see on [yalebulldogblue.com ](https://yalebulldogblue.com/)for Home and About Us, but do write something that is original. I don't want you to just copy paste the text from this website.

Then, on the products page, show product images from the catalogue, using the image paths that are in the database, with basic product info. This info should include name, price, and a short description. Make each product open a single-item page with a large image on one side and the full product text on the other complete with description, price, sizes/stock. Clicking on a card on the Products page should take the shopper to this single item page

Add a chat interface in the bottom right (just a little floating chat panel is what I'm after) that does not yet need to be an agent. This will just be a stub that we will have call a backend later on in a different part of the project

We need a small API to read the database. It's okay to just start using FastAPI app in backend/main.py to serve products and images and then grow this into the agent once we get further in the project. Go!

## Problem 4 — Create account and login
please build a normal create account and login flow that we see on lots of websites. The create account should have the user input first name last name email password (and confirm password). The login should be email and password. New accounts will be put into the users table. Please store passwords securely so that hackers can't access them.

the seed database has a test user that we can use while building, and the test user is test\@campuscustoms.yale.edu and the password is password. Confirm that this works so that we can log in as that user and make sure that a brand new accountn that we create also works. Update the harness.md file on how auth works (just say what we store for a user and how passwords are protected)

## Problem 5 — PydanticAI agent backend

Build the shop chatbot now as a pydanticAI agent behind FastAPI (which we already set up a bit). We are going to wire this into the front-end chat widget that we made and put the API app in backend/main.py. We will run this file with Uvicorn. Keep the agent as just these four files:

backend/prompts/prompt.md--a system prompt that we will grow

backend/agent.py--the agent entry and wiring

backend/tools.py--tools teh agent can call

backend/models.py--a pydanticAI structured type.

in main.py we need to expose a chat route so that a message from the website will return a reply from the pydanticai agent or whatever else is needed for products and authorization. We need the AI model API key for the agent.

Also, we need to put the campus customs voice and safety basics into the prompts.prompt.md file. We will start and update types in models.py for chat replies and product cards throughout this build process. Finally, in output/harness.md, we need to note how the front end talks to the FastAPI and how the agent is going to be loaded with the prompt file + the model. We also need to make sure the backend runs from backend folder in this way:

uvicorn main:app --reload --port 8000

### Follow-up prompts

well make the python environment and do it all again, unacceptable

do an audit of the pipeline we've done so far because it seems like you screwed some basic stuff up. Make sure it all works.

## Problem 6 — Tools: product info and stock

Now, please give the agent tools that look up the information from campus_customs.db which will include product description, price, and how many are in stock. The agent MUST USE THE DATABASE. It cannot invent any fake data regarding pricse or quantities. If a size is out of stock, then we need to very clearly say so.

Expand the prompts/prompt.md file so that the agent knows to call these tools for price and stock questions. Add or update the return types in models.py.

In output/harness.md, please list each tool and explain which model fields we chose for lookup results and why we did so. Thank you!

## Problem 7 — Chat search that updates the page

Okay. Now we need to add a feature to the site that makes it so that when a customer asks about a type of item, the agent searches the catalogue and then the website will dynamically show those matching items as product cards. An example query from the user could be "what hoodies do you have?"

this is an api contract: the agent returns structured product matches and then the front end renders them on the website. It's supposed to look super cool.

After the dynamic product cards are loaded by this new feature, we need to make sure the same single-item-page behavior that we built before still works. Each product card, including the ones that the chat just put on the page, still need to open the detail view with the large image and the full info when the user clicks on it. 

Update prompts/prompt.md and output/harness.md so that it is obvious how search results reach the page. Thank you!

## Problem 8 — Customer memory

Okay, now, when a shopper is logged into the website, you need to save their chat history in the database in the appropriate table and then reload it when they log back in. The agent needs to know who is chatting (meaning, the agent knows their name and email), and then we need to put that in agent deps or some sort of equivalent clear pattern that lets us keep track of this and/or the tools that the agent can call.

Also, we need to pass enough of the page context that if someone is on a page for a specific product and they ask a question about the specific product, the agent knows which item the user is referring to. We can put the code into the agent context to make this work.

Also, guests can still chat with the chatbot but the history only will persist for logged-in users. Please document all of this in output/harness.md and explain how user chat histroy is stored, what customer fields the agent sees, and how the page context is passed. Thank you!

### Follow-up prompts

Do a full audit of what we have so far and pretend you are a grader. Make sure that we are earning a 100%. This is a more complicated project than anything we have done together before.

## Problem 9 — Usability improvements

Now that the core shop is working, we need to make it even better! We need to do two front-end improvements and two backend improvements. What would you suggest we do as our two improvements for each end? Backend improvements would be things that make the agent output better or more accurate. These could be new tools or things that make the agent cheaper. What do you think we should do? Make some suggestions and I'll tell you what I want to do.

### Follow-up prompts

Let's do the following improvements then:

Frontend
1. Better product discovery
Add filters and sorting for garment type, color, sport/college, price, and size availability. This would make 102 products much easier to browse and would complement chatbot recommendations.
2. Stronger shopping/chat UX
Add loading states, suggested questions, clearer out-of-stock badges, and a saved-items/wishlist feature for logged-in shoppers. Chat results could include “View details” and “Save” actions.
Backend
1. Deterministic product-answer validation
Add a final validation layer that checks every product name, price, and size quantity in the agent response against SQLite. If the model says something unsupported, replace it with a safe database-backed answer. This would make hallucinated prices and stock nearly impossible.
2. Route simple questions around the LLM
Answer straightforward questions like “What is the price of this hoodie?” or “Is medium in stock?” directly from the database. Only send recommendation, styling, and ambiguous questions to PydanticAI. This would reduce cost and latency while improving factual accuracy.

Now, write output/usability.md. For each improvement that we just made, I want you to say what we added and why it helps a campus customs shopper or business. This should be easy since my last prompt had the improvements we're doing. Then, make sure all improvements actually show up in the app when it actually runs. The AI graders are going to read the write-up and look for the features that we added, so this is very important!

## Problem 10 — Style the website

Now, add a creative design so that the website feels like a real campus customs storefront. I want awesome colors, fonts, hierarchy, motion, product presentation, and chat feel. I want the design to mimic what you would do if you were the best web designer in the entire world. I'm thinking a really classic, oxford style of university vibe to it. In output/design.md, write wehat we changed and why it should help the customers want to stay on the website (because the website is so awesome). Make this description concrete and short

### Follow-up prompts

I couldn’t reach the Campus Customs stylist. Please make sure the FastAPI server is running.

I told you to audit the whole thing and it isnt' working. do better.

there we go. thank you. just to be safe do another full audit

## Problem 11 — Site testing (app check)

Now, please test the live site and document it in output/app_check.html, which will be a page that we can just double click to open. Include CLEAR SCREENSHOTS and short captions for 

chat checking the inventory of an item (honest stock/price from the database)

the dynamic search-result cards appearing after a category question (e.g. hoodies)

one of the two usability features that we added to the frontend a few prompts ago.

Make the HTML easy to grade by having a heading for each check, screenshot, one or two sentences on what the screenshot provides. Put the screenshot images in output/app_check_images and link them from app_check.html with relative paths (for example, app_check_images/inventory.png)

## Problem 12 — Audit trail, safety, finish harness

Keep an append-only output/audit\_trail.json of agent-loop activity. This should include time, tool name, short arguments, stop reason. Do not wipe this between runs, it should just keep appending.

Also, I want you to think of safety rules that we should give to the agent and put them all into prompts/prompt.md.

Then, I want you to finish output/harness.md so that it is clear how the entire system that we just built works. I want you to do the following four things:

model the fields in models.py and explain why you chose them

tools and abilities
safety rules
specs

### Follow-up prompts

the specs section should include loop limits, result caps, models, and how to run the frontend + backend