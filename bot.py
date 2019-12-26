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
error_generating_thumbnail = "⚠️ Sorry, <code>ffmpeg</code> seems unable to generate a thumbnail image for this file. Please, contact @Mike_Went"
error_wrong_url = "👀 This URL does not look like a .webm file"
error_huge_file = "🍉 File is bigger than 50 MB. Telegram <b>does not<b> allow me to upload huge files, sorry."
error_no_header = "🔬 WTF? I do not understand what server tries to give me instead of .webm file"
error_file_not_webm = "👀 This is not a .webm file. If you are sure it's an error, contact @Mike_Went"
error_converting = "⚠️ Sorry, <code>ffmpeg</code> seems unable to convert this file to MP4. Please, contact @Mike_Went"

message_start = """Hello! I am WebM to MP4 (H.264) converter bot 📺

You can send .webm files up to 20 MB via Telegram and receive converted videos up to ☁️ 50 MB back (from any source — link/document)."""
message_help = "Send me a link (http://...) to <b>webm</b> file or just .webm <b>document</b>"
message_starting = "🚀 Starting..."
message_converting = "☕️ Converting... {}"
message_generating_thumbnail = "🖼 Generating thumbnail.."
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
    global telegram_token
    filename = "".join([TEMP_FOLDER, random_string(), ".mp4"])

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
    allowed_mimes = ["video/webm", "application/octet-stream"]
    if r.headers["Content-Type"] not in allowed_mimes and message.document.mime_type not in allowed_mimes:
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

    # Start ffmpeg
    ffmpeg_process = subprocess.Popen(["ffmpeg",
        "-v", "error",
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
        time.sleep(1)
    except:
        update_status_message(status_message, error_downloading)
        # Close pipe explicitly
        os.close(pipe_read)
        return

    # While ffmpeg process is alive (i.e. is working)
    old_progress = ""
    while ffmpeg_process.poll() == None:
        try:
            output_file_size = os.stat(filename).st_size
        except FileNotFoundError:
            output_file_size = 0
        mp4_size = size(output_file_size, system=alternative)
        webm_size = size(int(r.headers["Content-Length"]), system=alternative)
        human_readable_progress = " ".join([mp4_size, "/", webm_size])
        if human_readable_progress != old_progress:
            update_status_message(status_message, message_converting.format(human_readable_progress))
            old_prpgress = human_readable_progress
        time.sleep(3)

    # Exit in case of error with ffmpeg
    if ffmpeg_process.returncode != 0:
        update_status_message(status_message, error_converting)
        # Clean up and close pipe explicitly
        rm(filename)
        os.close(pipe_read)
        return

    # Check output file size
    mp4_size = os.path.getsize(filename)
    if mp4_size >= MAXIMUM_FILESIZE_ALLOWED:
        update_status_message(status_message, error_huge_file)
        # Clean up and close pipe explicitly
        rm(filename)
        os.close(pipe_read)
        return

    # Close pipe after using
    os.close(pipe_read)

    # 1. Get video duration in seconds
    video_duration = subprocess.run(["ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        filename
    ], stdout=subprocess.PIPE).stdout.decode("utf-8").strip()
    video_duration = round(float(video_duration))

    # 2. Get video height and width
    video_props = subprocess.run(["ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries","stream=width,height",
        "-of", "csv=s=x:p=0",
        filename
    ], stdout=subprocess.PIPE).stdout.decode("utf-8").strip()
    video_width, video_height = video_props.split("x")

    # 3. Take one frame from the middle of the video
    update_status_message(status_message, message_generating_thumbnail)
    thumbnail = "".join([TEMP_FOLDER, random_string(), ".jpg"])
    generate_thumbnail_process = subprocess.Popen(["ffmpeg",
        "-v", "error",
        "-i", filename,
        "-vcodec", "mjpeg",
        "-vframes", "1",
        "-an", "-f", "rawvideo",
        "-ss", str(int(video_duration/2)),
        # keep the limit of 90px height/width (Telegram API) while preserving the aspect ratio
        "-vf", "scale='if(gt(iw,ih),90,trunc(oh*a/2)*2)':'if(gt(iw,ih),trunc(ow/a/2)*2,90)'",
        thumbnail
    ])

    # While process is alive (i.e. is working)
    while generate_thumbnail_process.poll() == None:
        time.sleep(1)

    # Exit in case of error with ffmpeg
    if generate_thumbnail_process.returncode != 0:
        update_status_message(status_message, error_generating_thumbnail)
        # Clean up
        rm(filename)
        rm(thumbnail)
        return

    # Upload to Telegram
    update_status_message(status_message, message_uploading)
    mp4 = open(filename, "rb")
    thumb = open(thumbnail, "rb")
    requests.post(
        f"https://api.telegram.org/bot{telegram_token}/sendVideo",
        data={
            "chat_id": message.chat.id,
            "duration": video_duration,
            "width": video_width,
            "height": video_height,
            "reply_to_message_id": message.message_id,
            "supports_streaming": True
        },
        files=[
            ("video", (random_string()+".mp4", mp4, "video/mp4")),
            ("thumb", (random_string()+".jpg", thumb, "image/jpeg"))
        ]
    )
    bot.delete_message(message.chat.id, status_message.message_id)

    # Clean up
    mp4.close()
    thumb.close()
    rm(filename)
    rm(thumbnail)


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


bot.polling(none_stop=True)
