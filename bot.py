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

from hurry.filesize import size, alternative

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
message_starting = "🚀 Starting..."
message_progress = "☕️ Converting... {}"
message_uploading = "☁️ Uploading to Telegram..."

def update_status_message(message, text):
    try:
        bot.edit_message_text(chat_id=message.chat.id,
                          message_id=message.message_id,
                          text=text, parse_mode="HTML")
    except:
        pass


def rm(filename):
    """Delete file (like 'rm' command)"""
    try:
        os.remove(filename)
    except:
        pass


def random_string(length=12):
    """Random string of uppercase ASCII and digits"""
    return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length))


def download_file(request, pipe_write):
    """Pass remote file to the local pipe"""
    with open(pipe_write, "wb") as f:
        for chunk in request:
            f.write(chunk)


def webm2mp4_worker(message, url):
    """Generic process spawned every time user sends a link or a file"""
    filename = TEMP_FOLDER + random_string() + ".mp4"

    # Tell user that we are working
    status_message = bot.reply_to(message, message_starting, parse_mode="HTML")

    # Try to download URL
    try:
        r = requests.get(url, stream=True, headers=HEADERS)
    except:
        update_status_message(status_message, error_downloading)
        return

    # Something went wrong on the server side
    if r.status_code != 200:
        update_status_message(status_message, error_wrong_code.format(r.status_code))
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

    # Create a pipe to pass downloading file to ffmpeg without delays
    pipe_read, pipe_write = os.pipe()

    # stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL to suppress ffmpeg output
    ffmpeg_process = subprocess.Popen(["ffmpeg",
        "-threads", str(FFMPEG_THREADS),
        "-i", "pipe:0", # read input from stdin
        "-map", "V:0?", # select video stream
        "-map", "0:a?", # ignore audio if doesn't exist
        "-c:v", "libx264", # specify video encoder
        "-max_muxing_queue_size", "9999", # https://trac.ffmpeg.org/ticket/6375
        "-movflags", "+faststart", # optimize for streaming
        "-preset", "slow", # https://trac.ffmpeg.org/wiki/Encode/H.264#a2.Chooseapresetandtune
        "-timelimit", "900", # prevent DoS (exit after 15 min)
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", # https://stackoverflow.com/questions/20847674/ffmpeg-libx264-height-not-divisible-by-2#20848224
        filename
    ], stdin=pipe_read)

    # Download file in and pass it to ffmpeg with pipe
    try:
        threading.Thread(
            target=download_file,
            kwargs={
                "request": r,
                "pipe_write": pipe_write
            }
        ).start()
        # Initial delay to start downloading 
        time.sleep(2)
    except:
        update_status_message(status_message, error_downloading)
        return

    # While ffmpeg process is alive (i.e. is working)
    while ffmpeg_process.poll() == None:
        time.sleep(3)
        output_file_size = os.stat(filename).st_size
        human_readable_progress = size(output_file_size, system=alternative) + " / " + \
                                  size(int(r.headers["Content-Length"]), system=alternative)
        update_status_message(status_message, message_progress.format(human_readable_progress))

    # Exit if ffmpeg crashed
    if ffmpeg_process.returncode != 0:
        update_status_message(status_message, error_converting)
        # Clean up
        rm(filename)
        return

    # Check output file size
    mp4_size = os.path.getsize(filename)
    if mp4_size >= MAXIMUM_FILESIZE_ALLOWED:
        update_status_message(status_message, error_huge_file)
        # Clean up
        rm(filename)
        return

    # Upload to Telegram
    update_status_message(status_message, message_uploading)
    mp4 = open(filename, "rb")
    bot.send_video(message.chat.id, mp4, reply_to_message_id=message.message_id, supports_streaming=True)
    bot.delete_message(message.chat.id, status_message.message_id)

    # Clean up
    rm(filename)

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
    threading.Thread(
        target=webm2mp4_worker,
        kwargs={
            "message": message,
            "url": url
        }
    ).start()

# Handle files
@bot.message_handler(content_types=["document"])
def handle_files(message):
    if message.document.mime_type != "video/webm":
        return
    file_id = message.document.file_id
    file_info = bot.get_file(file_id)
    url = "https://api.telegram.org/file/bot{0}/{1}".format(telegram_token, file_info.file_path)
    threading.Thread(
        target=webm2mp4_worker,
        kwargs={
            "message": message,
            "url": url
        }
    ).start()

bot.polling(none_stop=True, interval=3)
