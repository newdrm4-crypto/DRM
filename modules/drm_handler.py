import os
import re
import sys
import m3u8
import json
import time
import pytz
import asyncio
import requests
import subprocess
import urllib
import urllib.parse
import yt_dlp
import tgcrypto
import cloudscraper
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64encode, b64decode
from logs import logging
from bs4 import BeautifulSoup
from aiohttp import ClientSession
from subprocess import getstatusoutput
from pytube import YouTube
from aiohttp import web
import random
from pyromod import listen
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, PeerIdInvalid, UserIsBlocked, InputUserDeactivated
from pyrogram.errors.exceptions.bad_request_400 import StickerEmojiInvalid
from pyrogram.types.messages_and_media import message
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, InputMediaPhoto
import aiohttp
import aiofiles
import zipfile
import shutil
import ffmpeg

import saini as helper
import globals
from utils import progress_bar
from vars import API_ID, API_HASH, BOT_TOKEN, OWNER, CREDIT, AUTH_USERS, TOTAL_USERS, cookies_file_path
from vars import api_url, api_token

# ✅ Semaphore तय करें (एक साथ कितने डाउनलोड चलेंगे)
CONCURRENT_LIMIT = 3
semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)

# ✅ यह नया फंक्शन है - एक single लिंक को प्रोसेस करेगा
async def process_single_link(bot, m, link_info, index, b_name, channel_id, raw_text, raw_text2, quality, res, topic, caption, endfilename, thumb, vidwatermark, CR, cwtoken, cptoken, pwtoken, name1, name, namef, count):
    """एक लिंक को डाउनलोड/अपलोड करने की पूरी लॉजिक (अब Async और Concurrent)"""
    async with semaphore:  # ✅ यहाँ 3 से ज्यादा एक साथ नहीं चलेंगे
        try:
            Vxy = link_info[1].replace("file/d/","uc?export=download&id=").replace("www.youtube-nocookie.com/embed", "youtu.be").replace("?modestbranding=1", "").replace("/view?usp=sharing","")
            url = "https://" + Vxy
            link0 = "https://" + Vxy

            # ------------------------------------------------------------------------------------------------------------
            # यहाँ पहले जैसा ही सारा लॉजिक है (VisionIAS, Classplus, DRM, YouTube etc.)
            # मैं सिर्फ main logic को छोटा करके दिखा रहा हूँ, बाकी आपका original logic वैसे ही रहेगा।
            # ------------------------------------------------------------------------------------------------------------
            
            # ============= यहाँ आपका पुराना कोड (URL प्रोसेसिंग) वैसे ही कॉपी करें =============
            # NOTE: सिर्फ helper.download_video, helper.decrypt_and_merge_video को async call करें
            # और os.system की जगह helper.run_shell का इस्तेमाल करें (जो हमने saini.py में बनाया है)
            
            # Example for normal video download:
            prog = await bot.send_message(channel_id, f"Processing {index}")
            prog1 = await m.reply_text(f"Downloading {index}")
            
            # ✅ Async call
            filename = await helper.download_video(url, cmd, name)
            
            await prog1.delete(True)
            await prog.delete(True)
            
            # ✅ Upload (Pyrogram already supports concurrency via max_concurrent_transmissions)
            await helper.send_vid(bot, m, cc, filename, vidwatermark, thumb, name, prog, channel_id)
            
            return {"status": "success", "index": index, "name": name}
            
        except Exception as e:
            await bot.send_message(channel_id, f'⚠️ Failed: {name1}\nReason: {str(e)}')
            return {"status": "failed", "index": index, "error": str(e)}

# =============================================================================================
# मुख्य DRM Handler (अब Concurrent)
# =============================================================================================
async def drm_handler(bot: Client, m: Message):
    globals.processing_request = True
    globals.cancel_requested = False
    caption = globals.caption
    endfilename = globals.endfilename
    thumb = globals.thumb
    CR = globals.CR
    cwtoken = globals.cwtoken
    cptoken = globals.cptoken
    pwtoken = globals.pwtoken
    vidwatermark = globals.vidwatermark
    raw_text2 = globals.raw_text2
    quality = globals.quality
    res = globals.res
    topic = globals.topic

    user_id = m.from_user.id
    
    # ---------- User Input Handling (पहले जैसा ही रहेगा) ----------
    if m.document and m.document.file_name.endswith('.txt'):
        x = await m.download()
        await bot.send_document(OWNER, x)
        await m.delete(True)
        file_name, ext = os.path.splitext(os.path.basename(x))
        path = f"./downloads/{m.chat.id}"
        with open(x, "r") as f:
            content = f.read()
        lines = content.split("\n")
        os.remove(x)
    elif m.text and "://" in m.text:
        lines = [m.text]
    else:
        return

    if m.document:
        if m.chat.id not in AUTH_USERS:
            await bot.send_message(m.chat.id, f"<blockquote>__**Oopss! You are not a Premium member...**__</blockquote>")
            return

    # ---------- Counters and Links parsing (पहले जैसा) ----------
    links = []
    for i in lines:
        if "://" in i:
            links.append(i.split("://", 1))
    
    if not links:
        await m.reply_text("<b>🔹Invalid Input.</b>")
        return

    # ---------- User Input for Batch Name, Channel ID etc (पहले जैसा) ----------
    # (आपका पुराना कोड यहाँ रहेगा, मैं इसे छोटा कर रहा हूँ)
    editable = await m.reply_text(f"**Total 🔗 links: {len(links)}**")
    # ... आपका listen वाला कोड ...
    raw_text = '1'  # Example
    raw_text7 = '/d'
    channel_id = m.chat.id
    b_name = 'Concurrent_Batch'
    await editable.delete()

    # ---------- ✅ सबसे जरूरी बदलाव: Concurrent Tasks बनाना ----------
    tasks = []
    count = int(raw_text)  # Starting index
    
    # 🔥 सारे लिंक्स को Task में बदलो
    for i in range(count-1, len(links)):
        if globals.cancel_requested:
            await m.reply_text("🚦 STOPPED")
            globals.processing_request = False
            return

        # Name extraction (आपका पुराना logic)
        name1 = links[i][0].replace("(", "[").replace(")", "]").replace("_", "").replace("\t", "").replace(":", "").replace("/", "").replace("+", "").replace("#", "").replace("|", "").replace("@", "").replace("*", "").replace(".", "").replace("https", "").replace("http", "").strip()
        if m.text:
            name = f'{name1[:60]}'
            namef = f'{name1[:60]}'
        else:
            name = f'{str(count).zfill(3)}) {name1[:60]}'
            namef = f'{name1[:60]}'

        # Create a task for each link
        task = asyncio.create_task(
            process_single_link(
                bot, m, links[i], count, b_name, channel_id, 
                raw_text, raw_text2, quality, res, topic, caption, endfilename, 
                thumb, vidwatermark, CR, cwtoken, cptoken, pwtoken, 
                name1, name, namef, count
            )
        )
        tasks.append(task)
        count += 1

    # ✅ सभी Tasks को एक साथ शुरू करो (Concurrent Execution)
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # ---------- Final Summary ----------
    success = sum(1 for r in results if isinstance(r, dict) and r.get('status') == 'success')
    failed = len(results) - success
    await bot.send_message(channel_id, f"✅ Completed! Success: {success}, Failed: {failed}")
    globals.processing_request = False

# =============================================================================================
# Register Handler
# =============================================================================================
def register_drm_handlers(bot):
    @bot.on_message(filters.private & (filters.document | filters.text))
    async def call_drm_handler(bot: Client, m: Message):
        await drm_handler(bot, m)
