import os
import asyncio
import youtube_dl

from pornhub_api import PornhubApi
from pornhub_api.backends.aiohttp import AioHttpBackend
from youtube_dl.utils import DownloadError

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from pyrogram.errors import ChatAdminRequired, UserNotParticipant, ChatWriteForbidden

from PornHub.config import log_chat, sub_chat
from PornHub.plugins.function import download_progress_hook

if not os.path.exists("downloads"):
    os.makedirs("downloads")
    print("✅ Directory 'downloads' has been created")
else:
    print("✅ Directory 'downloads' already exists")

active_users = set()  # Menggunakan set untuk menyimpan pengguna yang aktif

async def run_async(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args, **kwargs)

def url(filter, client, update):
    return "www.pornhub" in update.text

url_filter = filters.create(url, name="url_filter")

@Client.on_message(filters.incoming & filters.private, group=-1)
@Client.on_edited_message(filters.incoming & filters.private, group=-1)
async def subscribe_channel(c: Client, u: Message):
    if not sub_chat:
        return
    try:
        await c.get_chat_member(sub_chat, u.from_user.id)
    except UserNotParticipant:
        # Create a URL to redirect user to the channel
        url = f"https://t.me/{sub_chat}" if sub_chat.isalpha() else (await c.get_chat(sub_chat)).invite_link
        await u.reply_text(
            f"Hi {u.from_user.first_name}!\n\nYou must join the redirected channel in order to use this bot, if you've done it, please restart this bot!\n\nUse » /restart",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("• Join Channel •", url=url)]]),
        )
        await u.stop_propagation()
    except ChatAdminRequired:
        await c.send_message(log_chat, "Can't manage the provided channel, make sure I'm the admin on the channel!")

@Client.on_inline_query()
async def inline_search(c: Client, q: InlineQuery):
    query = q.query
    backend = AioHttpBackend()
    api = PornhubApi(backend=backend)
    results = []

    try:
        src = await api.search.search(query)
    except ValueError:
        results.append(
            InlineQueryResultArticle(
                title="I can't found it!",
                description="The video can't be found, try again later.",
                input_message_content=InputTextMessageContent(message_text="Video not found!"),
            )
        )
        await q.answer(results, switch_pm_text="• Results •", switch_pm_parameter="start")
        return

    videos = src.videos
    await backend.close()

    for vid in videos:
        pornstars = ", ".join(v for v in vid.pornstars) if vid.pornstars else "N/A"
        categories = ", ".join(v for v in vid.categories) if vid.categories else "N/A"
        tags = ", #".join(v for v in vid.tags) if vid.tags else "N/A"

        results.append(
            InlineQueryResultArticle(
                title=vid.title,
                input_message_content=InputTextMessageContent(message_text=vid.url, disable_web_page_preview=True),
                description=f"Duration: {vid.duration}\nViews: {vid.views}\nRating: {vid.rating}",
                thumb_url=vid.thumb,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Watch in web", url=vid.url)]]),
            )
        )

    await q.answer(results, switch_pm_text="• Results •", switch_pm_parameter="start")

@Client.on_message(url_filter)
async def options(c: Client, m: Message):
    await m.reply_text(
        "Tap the button to continue action!", 
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Download", callback_data=f"d_{m.text}")],
            [InlineKeyboardButton("Watch in web", url=m.text)],
        ])
    )

@Client.on_callback_query(filters.regex("^d"))
async def get_video(c: Client, q: CallbackQuery):
    url = q.data.split("_", 1)[1]
    msg = await q.message.edit("Downloading...")
    user_id = q.message.from_user.id

    if user_id in active_users:
        await q.message.edit("Sorry, you can only download one video at a time!")
        return
    active_users.add(user_id)

    ydl_opts = {
        "progress_hooks": [lambda d: download_progress_hook(d, q.message, c)]
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            await run_async(ydl.download, [url])
        except DownloadError:
            await q.message.edit("Sorry, an error occurred during download.")
            active_users.remove(user_id)
            return

    # Cek jika ada file video yang diunduh
    video_file = None
    for file in os.listdir('.'):
        if file.endswith(".mp4"):
            video_file = file
            break

    # Kirim video dan thumbnail
    if video_file:
        thumbnail_path = "downloads/src/pornhub.jpeg"
        if os.path.exists(thumbnail_path):
            await q.message.reply_video(
                video=video_file,
                thumb=thumbnail_path,
                width=1280,
                height=720,
                caption="The content you requested has been successfully downloaded!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("• Donate •", url="https://t.me/Cvbmpoy")]])
            )
        else:
            await q.message.reply_video(
                video=video_file,
                caption="The content you requested has been successfully downloaded!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("• Donate •", url="https://t.me/Cvbmpoy")]])
            )
        os.remove(video_file)  # Hapus file video setelah dikirim
    else:
        await q.message.edit("No video file found.")

    await msg.delete()
    active_users.remove(user_id)
