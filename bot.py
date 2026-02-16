from flask import Flask, jsonify
from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError
)
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji

import asyncio
import threading
import os

app = Flask(__name__)

# ================= GLOBAL STORAGE =================
clients = {}
loops = {}
phones = {}

# ================= HELPERS =================
def run_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

def get_client(phone, api_id=None, api_hash=None):
    return TelegramClient(f"sessions/{phone}", api_id, api_hash)

# ================= USER PANEL =================
@app.route("/")
def home():
    return jsonify({
        "status": "running ✅",
        "routes": {
            "login_start": "/login/start/API_ID/API_HASH/PHONE",
            "login_otp": "/login/otp/PHONE/OTP",
            "login_password": "/login/password/PHONE/PASSWORD",
            "reaction_start": "/react/start/PHONE/GROUP_ID/EMOJI",
            "reaction_stop": "/react/stop/PHONE",
            "reaction_status": "/react/status/PHONE"
        }
    })

# ================= LOGIN START =================
@app.route("/login/start/<api_id>/<api_hash>/<phone>")
def login_start(api_id, api_hash, phone):
    try:
        api_id = int(api_id)

        if phone in clients:
            return jsonify({"status": "already_logged", "message": "Session exists ✅"})

        loop = asyncio.new_event_loop()
        threading.Thread(target=run_loop, args=(loop,), daemon=True).start()

        client = get_client(phone, api_id, api_hash)

        async def send_code():
            await client.connect()
            if await client.is_user_authorized():
                return {"status": "already_logged"}
            await client.send_code_request(phone)
            return {"status": "otp_sent"}

        result = asyncio.run_coroutine_threadsafe(send_code(), loop).result()

        clients[phone] = client
        loops[phone] = loop
        phones[phone] = {"api_id": api_id, "api_hash": api_hash}

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)})

# ================= LOGIN OTP =================
@app.route("/login/otp/<phone>/<otp>")
def login_otp(phone, otp):
    if phone not in clients:
        return jsonify({"error": "Start login first"})

    client = clients[phone]
    loop = loops[phone]

    async def do_login():
        try:
            await client.sign_in(phone, otp)
            return {"status": "login_success ✅"}
        except SessionPasswordNeededError:
            return {"status": "2fa_required"}
        except (PhoneCodeInvalidError, PhoneCodeExpiredError):
            return {"status": "otp_invalid ❌"}

    result = asyncio.run_coroutine_threadsafe(do_login(), loop).result()
    return jsonify(result)

# ================= LOGIN PASSWORD =================
@app.route("/login/password/<phone>/<password>")
def login_password(phone, password):
    if phone not in clients:
        return jsonify({"error": "Start login first"})

    client = clients[phone]
    loop = loops[phone]

    async def do_password():
        try:
            await client.sign_in(password=password)
            return {"status": "login_success ✅"}
        except Exception as e:
            return {"error": str(e)}

    result = asyncio.run_coroutine_threadsafe(do_password(), loop).result()
    return jsonify(result)

# ================= REACTION START =================
@app.route("/react/start/<phone>/<group_id>/<emoji>")
def reaction_start(phone, group_id, emoji):
    if phone not in clients:
        return jsonify({"error": "Login required"})

    client = clients[phone]
    loop = loops[phone]

    try:
        group_id = int(group_id)

        async def start_reaction():
            @client.on(events.NewMessage(chats=group_id))
            async def handler(event):
                try:
                    reaction = ReactionEmoji(emoticon=emoji)
                    await client(SendReactionRequest(
                        peer=await event.get_input_chat(),
                        msg_id=event.message.id,
                        reaction=[reaction]
                    ))
                except:
                    pass
            return {"status": "reaction_started 🔥"}

        result = asyncio.run_coroutine_threadsafe(start_reaction(), loop).result()
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)})

# ================= REACTION STOP =================
@app.route("/react/stop/<phone>")
def reaction_stop(phone):
    if phone not in clients:
        return jsonify({"error": "Not running"})

    client = clients[phone]
    loop = loops[phone]

    async def stop_client():
        await client.disconnect()
        return {"status": "stopped ✅"}

    result = asyncio.run_coroutine_threadsafe(stop_client(), loop).result()

    del clients[phone]
    del loops[phone]
    del phones[phone]

    return jsonify(result)

# ================= STATUS =================
@app.route("/react/status/<phone>")
def reaction_status(phone):
    if phone not in clients:
        return jsonify({"status": "offline ❌"})
    return jsonify({"status": "running 🔥", "phone": phone})

# ================= MAIN =================
if __name__ == "__main__":
    os.makedirs("sessions", exist_ok=True)
    # Flask standalone mode disabled; Render will use Gunicorn
