#!/usr/bin/env python3

# https://github.com/MikeWent/webm2mp4
# https://t.me/webm2mp4bot

import os
import random
import re
import string
import subprocess
import threading
import time

import requests
import telebot

# SETTINGS
TEMP_FOLDER = "/tmp/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.181 Safari/537.36",
    "Accept-Encoding": "identity"
}
MAXIMUM_FILESIZE_ALLOWED = 50*1024*1024 # ~50 MB
FFMPEG_THREADS = 4

# MESSAGES
error_wrong_code = "❗️ Resource returned HTTP {} code. Maybe link is broken"
error_downloading = "⚠️ Unable to download file"
error_converting = "⚠️ Sorry, <code>ffmpeg</code> seems unable to convert this file to MP4. Please, contact @Mike_Went"
error_wrong_url = "👀 This URL does not look like a .webm file"
error_huge_file = "🍉 File is bigger than 50 MB. Telegram <b>does not<b> allow me to upload huge files, sorry."
error_no_header = "🔬 WTF? I do not understand what server tries to give me instead of .webm file"
error_file_not_webm = "👀 This is not a .webm file"
message_start = """Hello! I am WebM to MP4 (H.264) converter bot 📺

You can send .webm files up to 20 MB via Telegram and receive converted videos up to ☁️ 50 MB back (from any source — link/document)."""
message_help = "Send me a link (http://...) to <b>webm</b> file or just .webm <b>document</b>"
message_downloading = "📡 Downloading file..."
message_progress = "☕️ Converting... {}"
message_uploading = "☁️ Uploading to Telegram..."

def update_status_message(message, text):
    bot.edit_message_text(chat_id=message.chat.id,
                          message_id=message.message_id,
                          text=text, parse_mode="HTML")

def rm(filename):
    """Delete file (like 'rm' command)"""
    try:
        os.remove(filename)
    except:
        pass

def random_string(length=12):
    """Random string of uppercase ASCII and digits"""
    return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length))

def webm2mp4_worker(message, url):
    """Generic process spawned every time user sends a link or a file"""
    # Generate temporary 12 symbols filename 
    filename = TEMP_FOLDER + random_string()
    # Tell user that we are working
    status_message = bot.reply_to(message, message_downloading, parse_mode="HTML")
    # Try to download URL
    try:
        r = requests.get(url, stream=True, headers=HEADERS)
    except:
        update_status_message(status_message, error_downloading)
        return
    # Something went wrong on the server side
    if r.status_code != 200:
        update_status_message(status_message, error_wrong_code.format(r.status_code))
        # Clean up
        rm(filename+".webm")
        return
    # Is it a webm file?
    if r.headers["Content-Type"] != "video/webm" and message.document.mime_type != "video/webm":
        update_status_message(status_message, error_file_not_webm)
        return
    # Can't determine file size
    if not "Content-Length" in r.headers or not "Content-Type" in r.headers:
        update_status_message(status_message, error_no_header)
        return
    # Check file size
    webm_size = int(r.headers["Content-Length"])
    if webm_size >= MAXIMUM_FILESIZE_ALLOWED: 
        update_status_message(status_message, error_huge_file)
        return
    # Buffered download
    try:
        with open(filename+".webm", "wb") as f:
            for chunk in r:
                f.write(chunk)
    except:
        update_status_message(status_message, error_downloading)
    # stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL to suppress ffmpeg output
    ffmpeg_process = subprocess.Popen(["ffmpeg",
        "-threads", str(FFMPEG_THREADS),
        "-i", filename+".webm",
        "-map", "V:0?", # select video stream
        "-map", "0:a?", # ignore audio if doesn't exist
        "-c:v", "libx264", # specify video encoder
        "-max_muxing_queue_size", "9999", # https://trac.ffmpeg.org/ticket/6375
        "-movflags", "+faststart", # optimize for streaming
        "-preset", "slow", # https://trac.ffmpeg.org/wiki/Encode/H.264#a2.Chooseapresetandtune
        "-timelimit", "900", # prevent DoS (exit after 15 min)
        filename+".mp4"
    ]) 
    ffmpeg_process_pid = ffmpeg_process.pid
    # While ffmpeg process is alive (i.e. is working)
    while ffmpeg_process.poll() == None:
        time.sleep(5)
        # get ffmpeg progress
        ffmpeg_progress = subprocess.run(["progress", "--quiet", "--pid", str(ffmpeg_process_pid)], stdout=subprocess.PIPE).stdout.decode("utf-8")
        if ffmpeg_progress == "":
            continue
        human_readable_progress = ffmpeg_progress.split("\n")[1].strip()
        update_status_message(status_message, message_progress.format(human_readable_progress))
    # Exit if ffmpeg crashed
    if ffmpeg_process.returncode != 0:
        update_status_message(status_message, error_converting)
        return
    # Check output file size
    mp4_size = os.path.getsize(filename+".mp4")
    if mp4_size >= MAXIMUM_FILESIZE_ALLOWED:
        update_status_message(status_message, error_huge_file)
        return
    # Upload to Telegram
    update_status_message(status_message, message_uploading)
    mp4 = open(filename+".mp4", "rb")
    bot.send_video(message.chat.id, mp4, reply_to_message_id=message.message_id, supports_streaming=True)
    bot.delete_message(message.chat.id, status_message.message_id)
    # Clean up
    rm(filename+".webm")
    rm(filename+".mp4")

### Telegram interaction below ###
try:
    with open("token.txt", "r") as f:
        telegram_token = f.read().strip()
except FileNotFoundError:
    print("Put your Telegram bot token to 'token.txt' file")
    exit(1)
bot = telebot.TeleBot(telegram_token)

@bot.message_handler(commands=["start", "help"])
def start_help(message):
    bot.send_message(message.chat.id, message_start, parse_mode="HTML")
    bot.send_message(message.chat.id, message_help, parse_mode="HTML")

# Handle URLs
URL_REGEXP = r"(http.?:\/\/.*\.webm)"
@bot.message_handler(regexp=URL_REGEXP)
def handle_urls(message):
    # Grab first found link
    url = re.findall(URL_REGEXP, message.text)[0]
    new_worker = threading.Thread(target=webm2mp4_worker, kwargs={"message": message, "url": url})
    new_worker.start()

# Handle files
@bot.message_handler(content_types=["document"])
def handle_files(message):
    if message.document.mime_type != "video/webm":
        return
    file_id = message.document.file_id
    file_info = bot.get_file(file_id)
    url = "https://api.telegram.org/file/bot{0}/{1}".format(telegram_token, file_info.file_path)
    new_worker = threading.Thread(target=webm2mp4_worker, kwargs={"message": message, "url": url})
    new_worker.start()

bot.polling(none_stop=True, interval=3)
