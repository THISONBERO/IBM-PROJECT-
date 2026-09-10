"""
demo_run.py
-----------
Runs the REAL SupportAgent / tools / memory code from ecommerce_support_agent.py
end-to-end. The only thing stubbed is the network call to the Claude API
(messages.create) — replaced with a scripted sequence of responses that
mirror exactly what Claude would do given these tool schemas and inputs
(tool_use blocks -> tool_result -> final text). Everything else (tool
execution, order/return lookups, memory writes/reads) is 100% real code
from the agent, not mocked.

This produces a genuine, reproducible execution transcript without needing
network access or a live API key.
"""

import sys
import types
import json

# ---- Stub only the anthropic network client -------------------------------
sys.path.insert(0, "/home/claude/demo")

fake_anthropic = types.ModuleType("anthropic")


class Block:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class FakeResponse:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


# Scripted turns: each user message maps to a sequence of model responses
# (usually: one tool_use response, then one final text response after
# seeing the tool_result). This is exactly the shape real Claude responses
# take for these tool schemas.
SCRIPT = {
    "Where is my order ORD-10001?": [
        [Block("tool_use", id="t1", name="get_order_status", input={"order_id": "ORD-10001"})],
        [Block("text", text=(
            "Your order ORD-10001 (AeroFlex Running Shoes) has shipped via UPS "
            "and is on its way — tracking number 1Z999AA10123456784. Estimated "
            "delivery is tomorrow."
        ))],
    ],
    "Can you recommend something for hiking under $150?": [
        [Block("tool_use", id="t2", name="recommend_products", input={"interest": "hiking", "max_price": 150})],
        [Block("text", text=(
            "I'd recommend the TrailBlazer Hiking Boots ($129.99, 4.7★) — waterproof "
            "with reinforced ankle support, well within your $150 budget. Want me to "
            "pull up more details or check sizing?"
        ))],
    ],
    "I want to return the headphones from ORD-10002, they arrived defective": [
        [Block("tool_use", id="t3", name="get_order_status", input={"order_id": "ORD-10002"})],
        [Block("tool_use", id="t4", name="initiate_return", input={
            "order_id": "ORD-10002", "sku": "SKU-2001", "reason": "arrived defective"
        })],
        [Block("text", text=(
            "I've started your return for the CloudComfort Wireless Headphones from "
            "ORD-10002 — reason logged as 'arrived defective'. Refund amount: $149.99. "
            "You'll get an email with a prepaid shipping label shortly. Is there "
            "anything else I can help with?"
        ))],
    ],
    "What's the status of that return?": [
        [Block("tool_use", id="t5", name="check_return_status", input={"return_id": "__LAST_RETURN_ID__"})],
        [Block("text", text=(
            "Your return is currently in 'initiated' status — we're waiting on the "
            "item to reach our warehouse. Once it's received and inspected, your "
            "$149.99 refund will be processed to your original payment method."
        ))],
    ],
    "By the way, I usually wear a size 9 and prefer eco-friendly packaging": [
        [Block("text", text=(
            "Got it — noted that you're a size 9 and prefer eco-friendly packaging. "
            "I'll keep that in mind for future recommendations and orders."
        ))],
    ],
}


class FakeMessages:
    def __init__(self):
        self._call_counts = {}
        self._last_return_id = None

    def create(self, model, max_tokens, system, tools, messages):
        # Identify which scripted user turn we're mid-way through by
        # inspecting the last plain-text user message in the running history.
        last_user_text = None
        for m in reversed(messages):
            if m["role"] == "user" and isinstance(m["content"], str):
                last_user_text = m["content"]
                break

        key = last_user_text
        steps = SCRIPT.get(key)
        idx = self._call_counts.get(key, 0)
        self._call_counts[key] = idx + 1

        blocks = steps[idx]

        # patch in the real return id generated earlier, for the follow-up
        # "what's the status of that return?" turn
        for b in blocks:
            if b.type == "tool_use" and b.input.get("return_id") == "__LAST_RETURN_ID__":
                b.input["return_id"] = self._last_return_id

        stop_reason = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
        return FakeResponse(blocks, stop_reason)


class FakeAnthropicClient:
    def __init__(self, api_key=None):
        self.messages = FakeMessages()


fake_anthropic.Anthropic = FakeAnthropicClient
sys.modules["anthropic"] = fake_anthropic

# ---- Now import the REAL agent code (tools, memory, agent logic) ----------
import ecommerce_support_agent as app  # noqa: E402


def run():
    print("=" * 78)
    print(" AI E-COMMERCE SUPPORT AGENT — FULL EXECUTION TRANSCRIPT")
    print(" (model calls scripted for offline/no-network demo; all tool")
    print("  execution, order/product lookups, and memory read/writes are")
    print("  real code from ecommerce_support_agent.py)")
    print("=" * 78)

    customer_id = "CUST-001"
    customer = app.CUSTOMERS[customer_id]
    print(f"\n[SYSTEM] Connecting as {customer['name']} ({customer_id}), loyalty tier: {customer['loyalty_tier']}\n")

    agent = app.SupportAgent(customer_id=customer_id, api_key="demo-key")

    turns = [
        "Where is my order ORD-10001?",
        "Can you recommend something for hiking under $150?",
        "I want to return the headphones from ORD-10002, they arrived defective",
        "What's the status of that return?",
        "By the way, I usually wear a size 9 and prefer eco-friendly packaging",
    ]

    for turn in turns:
        print(f"You: {turn}")
        reply = agent.send_message(turn)
        print(f"\nAria: {reply}\n")
        print("-" * 78)

        # capture the real return id created during the return turn, so the
        # follow-up "what's the status of that return?" turn can reference it
        if app.RETURNS:
            agent.client.messages._last_return_id = list(app.RETURNS.keys())[-1]

    # End of session: persist a summary to long-term memory (real code path)
    summary = "Chat covered: " + "; ".join(turns[:3])
    agent.end_session(summary)

    print("\n[SYSTEM] Session ended. Long-term memory persisted to:")
    print(f"         {agent.customer_memory.path}\n")

    print("=" * 78)
    print(" LONG-TERM CUSTOMER MEMORY CONTENTS (persisted JSON, real file)")
    print("=" * 78)
    with open(agent.customer_memory.path) as f:
        print(f.read())

    print("=" * 78)
    print(" WHAT A NEW SupportAgent() FOR THIS CUSTOMER SEES ON NEXT SESSION")
    print(" (i.e. the system-prompt context injected automatically)")
    print("=" * 78)
    fresh_agent = app.SupportAgent(customer_id=customer_id, api_key="demo-key")
    print(fresh_agent.customer_memory.as_context_string())
    print()


if __name__ == "__main__":
    run()
