from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
)
from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID, PAYMENT_PROVIDER_TOKEN, MONGO_URI
from pymongo import MongoClient
from datetime import datetime, timedelta

app = Client("audio_payment_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

client = MongoClient(MONGO_URI)
db = client["audio_bot"]
users = db["users"]
playlist = db["playlist"]

AUDIO_PRICE = 49
ACCESS_DURATION = timedelta(days=1)
LANG = {"en": {}, "ta": {}}

# English
LANG["en"]["welcome"] = "👋 Welcome! Type /buy to purchase premium audio."
LANG["en"]["paid"] = "✅ Payment successful! Access valid until {}"
LANG["en"]["play"] = "▶️ Playing track {} of {}"
LANG["en"]["expired"] = "⚠️ Your access expired. Use /buy to get access again."
LANG["en"]["upload_success"] = "✅ Track added to playlist."
LANG["en"]["queue_empty"] = "📭 Playlist is empty."
LANG["en"]["already_paid"] = "✅ You already have access until {}"

# Tamil
LANG["ta"]["welcome"] = "👋 வரவேற்கிறோம்! பிரீமியம் ஆடியோக்கள் பெற /buy பயன்படுத்தவும்."
LANG["ta"]["paid"] = "✅ கட்டணம் பெற்றது! உங்கள் அணுகல் {} வரை செல்லுபடியாகும்."
LANG["ta"]["play"] = "▶️ பாடல் {} / {}"
LANG["ta"]["expired"] = "⚠️ உங்கள் அணுகல் காலாவதியானது. மீண்டும் /buy பயன்படுத்தவும்."
LANG["ta"]["upload_success"] = "✅ பாடல் வெற்றிகரமாக சேர்க்கப்பட்டது."
LANG["ta"]["queue_empty"] = "📭 பிளேலிஸ்ட் காலியாக உள்ளது."
LANG["ta"]["already_paid"] = "✅ நீங்கள் ஏற்கனவே {} வரை அணுகலுடன் இருக்கிறீர்கள்."

def get_lang(user):
    record = users.find_one({"user_id": user})
    return record["lang"] if record and "lang" in record else "en"

@app.on_message(filters.command("start"))
async def start(client, message: Message):
    user = message.from_user.id
    users.update_one({"user_id": user}, {"$setOnInsert": {"user_id": user, "lang": "en"}}, upsert=True)
    await message.reply_text("🌐 Choose Language / மொழியைத் தேர்ந்தெடுக்கவும்", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
         InlineKeyboardButton("🇮🇳 தமிழ்", callback_data="lang_ta")]
    ]))

@app.on_callback_query()
async def set_language(client, callback):
    lang = callback.data.split("_")[1]
    user = callback.from_user.id
    users.update_one({"user_id": user}, {"$set": {"lang": lang}}, upsert=True)
    await callback.message.edit_text(LANG[lang]["welcome"])

@app.on_message(filters.command("buy"))
async def buy_audio(client, message: Message):
    user_id = message.from_user.id
    lang = get_lang(user_id)
    record = users.find_one({"user_id": user_id})
    if record and "expiry" in record and record["expiry"] > datetime.now():
        await message.reply_text(LANG[lang]["already_paid"].format(record["expiry"].strftime("%Y-%m-%d %H:%M:%S")))
        return

    await client.send_invoice(
        chat_id=message.chat.id,
        title="Premium Audio Access",
        description="Unlock all playlist tracks",
        payload="audio_payment_payload",
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency="INR",
        prices=[LabeledPrice("Access", AUDIO_PRICE * 100)],
        start_parameter="audio_access",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Pay Now 💳", pay=True)]])
    )

@app.on_message(filters.successful_payment)
async def payment_success(client, message: Message):
    user_id = message.from_user.id
    expiry_time = datetime.now() + ACCESS_DURATION
    users.update_one({"user_id": user_id}, {"$set": {"expiry": expiry_time}}, upsert=True)
    lang = get_lang(user_id)
    await message.reply_text(LANG[lang]["paid"].format(expiry_time.strftime("%Y-%m-%d %H:%M:%S")))
    await play_audio(client, message)

async def play_audio(client, message: Message):
    user_id = message.from_user.id
    lang = get_lang(user_id)
    record = users.find_one({"user_id": user_id})
    if not record or "expiry" not in record or record["expiry"] < datetime.now():
        await message.reply_text(LANG[lang]["expired"])
        return

    tracks = list(playlist.find())
    if not tracks:
        await message.reply_text(LANG[lang]["queue_empty"])
        return

    for idx, track in enumerate(tracks, 1):
        await message.reply_audio(
            track["file_id"],
            caption=LANG[lang]["play"].format(idx, len(tracks))
        )

@app.on_message(filters.command("play"))
async def user_play(client, message: Message):
    await play_audio(client, message)

@app.on_message(filters.command("uploadaudio") & filters.user(ADMIN_ID))
async def admin_upload(client, message: Message):
    if not message.reply_to_message or not message.reply_to_message.audio:
        await message.reply_text("❗ Reply to an audio to add to playlist.")
        return
    audio = message.reply_to_message.audio
    playlist.insert_one({"file_id": audio.file_id, "title": audio.title})
    await message.reply_text("✅ Audio added to playlist.")

app.run()