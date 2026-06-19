import os
import re
import time
import mmap
import datetime
import aiohttp
import aiofiles
import asyncio
import logging
import requests
import tgcrypto
import subprocess
from math import ceil
from utils import progress_bar
from pyrogram import Client, filters
from pyrogram.types import Message
from io import BytesIO
from pathlib import Path
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode

# ============================================================
# ✅ नया Async Shell हेल्पर – सभी कमांड्स इसी से चलेंगे
# ============================================================
async def run_shell(cmd: str) -> tuple[int, str, str]:
    """
    Run a shell command asynchronously.
    Returns: (returncode, stdout, stderr)
    """
    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return process.returncode, stdout.decode(), stderr.decode()

# ============================================================
# ✅ duration – ffprobe (sync रह सकता है, क्योंकि यह एक quick call है)
# ============================================================
def duration(filename):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-of",
         "default=noprint_wrappers=1:nokey=1", filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    return float(result.stdout)

# ============================================================
# ✅ get_mps_and_keys – (sync, because it's just a network request)
# ============================================================
def get_mps_and_keys(api_url):
    response = requests.get(api_url)
    response_json = response.json()
    mpd = response_json.get('url')
    keys = response_json.get('keys')
    return mpd, keys

# ============================================================
# ❌ पुराना exec और pull_run हटा दिया (ThreadPoolExecutor की जरूरत नहीं)
# ============================================================

# ============================================================
# ✅ PDF डाउनलोड – Async (aiohttp + aiofiles)
# ============================================================
async def aio(url, name):
    k = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(k, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return k

async def download(url, name):
    ka = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(ka, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return ka

# ============================================================
# ✅ parse_vid_info / vid_info – (sync, text parsing only)
# ============================================================
def parse_vid_info(info):
    info = info.strip()
    info = info.split("\n")
    new_info = []
    temp = []
    for i in info:
        i = str(i)
        if "[" not in i and '---' not in i:
            while "  " in i:
                i = i.replace("  ", " ")
            i.strip()
            i = i.split("|")[0].split(" ", 2)
            try:
                if "RESOLUTION" not in i[2] and i[2] not in temp and "audio" not in i[2]:
                    temp.append(i[2])
                    new_info.append((i[0], i[2]))
            except:
                pass
    return new_info

def vid_info(info):
    info = info.strip()
    info = info.split("\n")
    new_info = dict()
    temp = []
    for i in info:
        i = str(i)
        if "[" not in i and '---' not in i:
            while "  " in i:
                i = i.replace("  ", " ")
            i.strip()
            i = i.split("|")[0].split(" ", 3)
            try:
                if "RESOLUTION" not in i[2] and i[2] not in temp and "audio" not in i[2]:
                    temp.append(i[2])
                    new_info.update({f'{i[2]}': f'{i[0]}'})
            except:
                pass
    return new_info

# ============================================================
# ✅ decrypt_and_merge_video – पूरी तरह Async (DRM वीडियो)
# ============================================================
async def decrypt_and_merge_video(mpd_url, keys_string, output_path, output_name, quality="720"):
    try:
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        cmd1 = f'yt-dlp -f "bv[height<={quality}]+ba/b" -o "{output_path}/file.%(ext)s" --allow-unplayable-format --no-check-certificate --external-downloader aria2c "{mpd_url}"'
        print(f"Running: {cmd1}")
        await run_shell(cmd1)  # ✅ Async

        avDir = list(output_path.iterdir())
        print(f"Downloaded files: {avDir}")
        print("Decrypting")

        video_decrypted = False
        audio_decrypted = False

        for data in avDir:
            if data.suffix == ".mp4" and not video_decrypted:
                cmd2 = f'mp4decrypt {keys_string} --show-progress "{data}" "{output_path}/video.mp4"'
                print(f"Running: {cmd2}')
                await run_shell(cmd2)  # ✅ Async
                if (output_path / "video.mp4").exists():
                    video_decrypted = True
                data.unlink()
            elif data.suffix == ".m4a" and not audio_decrypted:
                cmd3 = f'mp4decrypt {keys_string} --show-progress "{data}" "{output_path}/audio.m4a"'
                print(f"Running: {cmd3}")
                await run_shell(cmd3)  # ✅ Async
                if (output_path / "audio.m4a").exists():
                    audio_decrypted = True
                data.unlink()

        if not video_decrypted or not audio_decrypted:
            raise FileNotFoundError("Decryption failed: video or audio file not found.")

        # ✅ FFmpeg को -preset veryfast और -threads 4 देकर तेज़ करें
        cmd4 = f'ffmpeg -i "{output_path}/video.mp4" -i "{output_path}/audio.m4a" -c copy -preset veryfast -threads 4 "{output_path}/{output_name}.mp4"'
        print(f"Running: {cmd4}")
        await run_shell(cmd4)  # ✅ Async

        if (output_path / "video.mp4").exists():
            (output_path / "video.mp4").unlink()
        if (output_path / "audio.m4a").exists():
            (output_path / "audio.m4a").unlink()

        filename = output_path / f"{output_name}.mp4"
        if not filename.exists():
            raise FileNotFoundError("Merged video file not found.")

        # Duration info – optional, sync is fine
        cmd5 = f'ffmpeg -i "{filename}" 2>&1 | grep "Duration"'
        duration_info = os.popen(cmd5).read()
        print(f"Duration info: {duration_info}")

        return str(filename)

    except Exception as e:
        print(f"Error during decryption and merging: {str(e)}")
        raise

# ============================================================
# ✅ run – पहले से Async है, ठीक है
# ============================================================
async def run(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    print(f'[{cmd!r} exited with {proc.returncode}]')
    if proc.returncode == 1:
        return False
    if stdout:
        return f'[stdout]\n{stdout.decode()}'
    if stderr:
        return f'[stderr]\n{stderr.decode()}'

# ============================================================
# ✅ old_download – sync, fine (rarely used)
# ============================================================
def old_download(url, file_name, chunk_size=1024 * 10):
    if os.path.exists(file_name):
        os.remove(file_name)
    r = requests.get(url, allow_redirects=True, stream=True)
    with open(file_name, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                fd.write(chunk)
    return file_name

# ============================================================
# ✅ human_readable_size / time_name – सिंपल sync functions
# ============================================================
def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024.0 or unit == 'PB':
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"

def time_name():
    date = datetime.date.today()
    now = datetime.datetime.now()
    current_time = now.strftime("%H%M%S")
    return f"{date} {current_time}.mp4"

# ============================================================
# ✅ download_video – पूरी तरह Async (सबसे महत्वपूर्ण)
# ============================================================
async def download_video(url, cmd, name):
    global failed_counter
    # ✅ Aria2 के साथ तेज़ डाउनलोड – x16 connections, 32 parallel chunks
    download_cmd = f'{cmd} -R 25 --fragment-retries 25 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32"'
    print(f"Download command: {download_cmd}")
    logging.info(download_cmd)

    retcode, stdout, stderr = await run_shell(download_cmd)  # ✅ Async

    # Retry logic for visionias (अगर fail हो तो 10 बार तक retry)
    if "visionias" in cmd and retcode != 0 and failed_counter <= 10:
        failed_counter += 1
        await asyncio.sleep(5)
        return await download_video(url, cmd, name)  # ✅ recursive async call

    failed_counter = 0

    # Check for downloaded file
    try:
        if os.path.isfile(name):
            return name
        elif os.path.isfile(f"{name}.webm"):
            return f"{name}.webm"
        name_base = name.split(".")[0]
        if os.path.isfile(f"{name_base}.mkv"):
            return f"{name_base}.mkv"
        elif os.path.isfile(f"{name_base}.mp4"):
            return f"{name_base}.mp4"
        elif os.path.isfile(f"{name_base}.mp4.webm"):
            return f"{name_base}.mp4.webm"
        return name
    except FileNotFoundError:
        # fallback
        return f"{name}.mp4"

# ============================================================
# ✅ send_doc – Async (पहले से ही async है, सिर्फ time.sleep को asyncio.sleep करें)
# ============================================================
async def send_doc(bot: Client, m: Message, cc, ka, cc1, prog, count, name, channel_id):
    reply = await bot.send_message(channel_id, f"Downloading pdf:\n<pre><code>{name}</code></pre>")
    await asyncio.sleep(1)   # ✅ time.sleep → asyncio.sleep
    start_time = time.time()
    await bot.send_document(ka, caption=cc1)
    count += 1
    await reply.delete(True)
    await asyncio.sleep(1)   # ✅
    os.remove(ka)
    await asyncio.sleep(3)   # ✅

# ============================================================
# ✅ decrypt_file – sync, fine (uses mmap)
# ============================================================
def decrypt_file(file_path, key):
    if not os.path.exists(file_path):
        return False
    with open(file_path, "r+b") as f:
        num_bytes = min(28, os.path.getsize(file_path))
        with mmap.mmap(f.fileno(), length=num_bytes, access=mmap.ACCESS_WRITE) as mmapped_file:
            for i in range(num_bytes):
                mmapped_file[i] ^= ord(key[i]) if i < len(key) else i
    return True

# ============================================================
# ✅ download_and_decrypt_video – पहले से async, ठीक है
# ============================================================
async def download_and_decrypt_video(url, cmd, name, key):
    video_path = await download_video(url, cmd, name)
    if video_path:
        decrypted = decrypt_file(video_path, key)
        if decrypted:
            print(f"File {video_path} decrypted successfully.")
            return video_path
        else:
            print(f"Failed to decrypt {video_path}.")
            return None

# ============================================================
# ✅ send_vid – सभी subprocess.run को run_shell में बदलें
# ============================================================
async def send_vid(bot: Client, m: Message, cc, filename, vidwatermark, thumb, name, prog, channel_id):
    # Thumbnail generate – async
    await run_shell(f'ffmpeg -i "{filename}" -ss 00:00:10 -vframes 1 "{filename}.jpg"')

    await prog.delete(True)
    reply1 = await bot.send_message(channel_id, f"**📩 Uploading Video 📩:-**\n<blockquote>**{name}**</blockquote>")
    reply = await m.reply_text(f"**Generate Thumbnail:**\n<blockquote>**{name}**</blockquote>")

    try:
        if thumb == "/d":
            thumbnail = f"{filename}.jpg"
        else:
            thumbnail = thumb

        if vidwatermark == "/d":
            w_filename = filename
        else:
            w_filename = f"w_{filename}"
            font_path = "vidwater.ttf"
            # Watermark – async
            await run_shell(
                f'ffmpeg -i "{filename}" -vf "drawtext=fontfile={font_path}:text=\'{vidwatermark}\':fontcolor=white@0.3:fontsize=h/6:x=(w-text_w)/2:y=(h-text_h)/2" -codec:a copy "{w_filename}"'
            )
    except Exception as e:
        await m.reply_text(str(e))

    dur = int(duration(w_filename))
    start_time = time.time()

    try:
        await bot.send_video(
            channel_id, w_filename, caption=cc,
            supports_streaming=True, height=720, width=1280,
            thumb=thumbnail, duration=dur,
            progress=progress_bar, progress_args=(reply, start_time)
        )
    except Exception:
        await bot.send_document(
            channel_id, w_filename, caption=cc,
            progress=progress_bar, progress_args=(reply, start_time)
        )

    os.remove(w_filename)
    await reply.delete(True)
    await reply1.delete(True)
    os.remove(f"{filename}.jpg")
