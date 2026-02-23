import chainlit as cl
from groq import Groq
import tiktoken
import uuid
from database import SessionLocal, Conversation
from cache import save_session, load_session

MODEL_NAME = "gpt-4o-mini"  # tokenizer reference only
MAX_INPUT_TOKENS = 6000  # reserve space for response
client = Groq(api_key="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")

@cl.on_chat_start
async def start():
   session_id = str(uuid.uuid4())
   cl.user_session.set("session_id", session_id)

   history = [
        {"role": "system", "content": "You are a helpful AI assistant."}
    ]

   save_session(session_id, history)
   cl.user_session.set("history", history)



@cl.on_message
async def main(message: cl.Message):

    session_id = cl.user_session.get("session_id")

    # 1️⃣ Load session from Redis
    history = load_session(session_id)

    if history is None:
        history = [
            {"role": "system", "content": "You are a helpful AI assistant."}
        ]

    # 2️⃣ Append user message
    history.append({"role": "user", "content": message.content})

    # 3️⃣ Dynamic compression BEFORE inference
    if count_tokens(history) > MAX_INPUT_TOKENS:
        history = compress_history_dynamically(history)

    # 4️⃣ Streaming LLM Call
    msg = cl.Message(content="")
    await msg.send()

    stream = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=history,
        stream=True,
    )

    full_reply = ""

    for chunk in stream:
        if chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content
            full_reply += token
            await msg.stream_token(token)

    # 5️⃣ Append assistant reply
    history.append({"role": "assistant", "content": full_reply})

    # 6️⃣ Save to Redis
    save_session(session_id, history)

    # 7️⃣ Save to Postgres
    db = SessionLocal()

    db.add(Conversation(session_id=session_id, role="user", content=message.content))
    db.add(Conversation(session_id=session_id, role="assistant", content=full_reply))

    db.commit()
    db.close()


def compress_history_dynamically(history):

    while count_tokens(history) > MAX_INPUT_TOKENS:

        # Find oldest non-system message index
        oldest_index = None

        for i in range(1, len(history)):
            if history[i]["role"] != "system":
                oldest_index = i
                break

        if oldest_index is None:
            break  # nothing to compress

        # Take small chunk starting from oldest message
        chunk = history[oldest_index: oldest_index + 4]

        # If chunk too small, just remove oldest message
        if len(chunk) < 2:
            history.pop(oldest_index)
            continue

        # Summarize chunk
        summary = summarize_messages(chunk)

        # Replace chunk with summarized memory
        history = (
            history[:oldest_index]
            + [{
                "role": "system",
                "content": f"Compressed memory: {summary}"
            }]
            + history[oldest_index + len(chunk):]
        )

    return history

def summarize_messages(messages):
    summary_prompt = [
        {"role": "system", "content": "Summarize the following conversation briefly but preserve important context, decisions, and facts."},
        {"role": "user", "content": str(messages)}
    ]

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=summary_prompt,
    )

    return response.choices[0].message.content

def count_tokens(messages):
    encoding = tiktoken.encoding_for_model(MODEL_NAME)
    total_tokens = 0

    for msg in messages:
        total_tokens += len(encoding.encode(msg["content"]))

    return total_tokens