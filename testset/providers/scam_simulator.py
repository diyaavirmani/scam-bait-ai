"""Promptfoo python provider that runs one persona-vs-scammer conversation (max 20 persona turns).
Scammer = Cerebras gpt-oss-120b playing a seed from conversations.jsonl. Persona = the arm under test
(A: Cerebras via Agents SDK OpenAIChatCompletionsModel + in-process session, full history each turn;
 B: OpenAI Responses + Conversations API). Conversation is never written to the DB. Returns transcript + metrics JSON:
turns_sustained, early_recall (message-1 probe at turn 15+), intel_extracted (vs seed.reveal), ai_revealed (judge), pii_leak (regex). Skeleton only."""
def call_api(prompt, options, context):
    raise NotImplementedError("wire to app.agents.persona + session store on build day")
