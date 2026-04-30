from crewai import Agent, Crew, Task, Process

from tools import (
    display_merch_images,
    get_item_stock,
    list_all_items,
    place_order,
)

SYSTEM_PROMPT = """\
You are a helpful store assistant for the Python Merch store.
You help customers find products and create orders.
Use the available tools to look up inventory information when asked.
When the user asks to see or browse items, use the display_merch_images tool to show visual cards.
Be concise and friendly in your responses.
Allow the user to add products to the order, and print the order content if the user requests it.

MERCH DISPLAY RULE:
When the display_merch_images tool returns results, you MUST embed a <merch-items> JSON block verbatim in your response.
Place the <merch-items> block at the start of your response, then add your message after it.
Do not paraphrase, reformat, or omit the block.

ORDER CONFIRMATION RULE:
After the place_order tool returns successfully, you MUST embed an <order-placed> block immediately before your confirmation text.
The block must contain a JSON object with:
  - orderId: the order ID string from the tool result (e.g. "A1B2C3D4")
  - items: array of { name: "<projectName> <type>", quantity: <number>, unitPrice: <number> }
  - total: total price as a number
Example:
<order-placed>{"orderId":"A1B2C3D4","items":[{"name":"NumPy T-Shirt","quantity":2,"unitPrice":29.99},{"name":"Pandas Sticker","quantity":3,"unitPrice":4.99}],"total":74.95}</order-placed>
Then follow with your friendly confirmation message.
"""

tools = [get_item_stock, display_merch_images, place_order, list_all_items]

store_agent = Agent(
    role="Crew AI Merch Store Assistant",
    goal="Help customers find products, browse inventory, and place orders at the Crew AI Merch Store",
    backstory=SYSTEM_PROMPT,
    llm="anthropic/claude-sonnet-4-6",
    tools=tools,
    verbose=False,
    memory=False,
    allow_delegation=False,
)


def create_crew_for_message(
    user_message: str, conversation_history: str, *, stream: bool = False
) -> Crew:
    """Create a single-task crew for one user message."""

    if conversation_history:
        task_description = (
            f"Previous conversation:\n{conversation_history}\n\n"
            f"Current customer message: {user_message}\n\n"
            f"Respond helpfully to the customer. Use your tools when needed to look up "
            f"inventory or place orders."
        )
    else:
        task_description = (
            f"Customer message: {user_message}\n\n"
            f"Respond helpfully to the customer. Use your tools when needed to look up "
            f"inventory or place orders."
        )

    task = Task(
        description=task_description,
        expected_output="A helpful response to the customer about Python merch products.",
        agent=store_agent,
    )

    return Crew(
        agents=[store_agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
        stream=stream,
    )
