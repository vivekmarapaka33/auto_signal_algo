from telethon import TelegramClient, events

api_id = "34919919"
api_hash = "aff94924e0ac7ea459d02578204d8954"


# Telegram session (saved locally)
client = TelegramClient("session", api_id, api_hash)

# Your group chat ID
GROUP_ID = -1002094899538


async def fetch_past_messages():
    print("📥 Fetching last 10 messages...\n")

    messages = []
    async for msg in client.iter_messages(GROUP_ID, limit=10):
        messages.append(msg)

    # Reverse to show oldest message first
    messages = list(reversed(messages))

    print("===== LAST 10 MESSAGES (Oldest → Newest) =====\n")
    for m in messages:
        print(f"[{m.date}] {m.sender_id}: {m.text}")
    print("\n==============================================\n")


# -------------------------------------------------
# LIVE MESSAGE LISTENER
# -------------------------------------------------
@client.on(events.NewMessage(chats=GROUP_ID))
async def live_message_handler(event):
    sender = await event.get_sender()
    sender_name = sender.first_name if sender else "Unknown"

    print("\n🔴 LIVE MESSAGE")
    print(f"From: {sender_name} ({event.sender_id})")
    print(f"Message: {event.raw_text}")
    print("----------------------------------------------")


async def main():
    await fetch_past_messages()
    print("👀 Now watching for live messages...\n")
    await client.run_until_disconnected()


# -------------------------------------------------
# START CLIENT
# -------------------------------------------------
client.start()
client.loop.run_until_complete(main())


# Vivek9346+-*/