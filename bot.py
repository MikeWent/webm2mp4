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
import json

import requests
import telebot

from hurry.filesize import size, alternative


# SETTINGS
MAXIMUM_FILESIZE_ALLOWED = 50 * 1024 * 1024  # ~50 MB
ALLOWED_MIME_TYPES_VIDEO = (
    "video/webm",
    "video/mp4",
    "application/octet-stream",
    "image/gif",
)
ALLOWED_MIME_TYPES_IMAGE = ("image/webp", "application/octet-stream")

# MESSAGES
class Message:
    start = """Hello! I am WebM to MP4 (H.264) and WebP to JPG converter bot 📺

You can send .webm files up to 20 MB via Telegram and receive converted videos up to ☁️ 50 MB back (from any source — link/document). Or you can send .webp files and receive converted jpg image"""
    help = "Send me a link (http://...) to <b>webm</b> or <b>webp</b> file or just .webm or .webp <b>document</b>"
    starting = "🚀 Starting..."
    converting = "☕️ Converting... {}"
    generating_thumbnail = "🖼 Generating thumbnail.."
    uploading = "☁️ Uploading to Telegram..."


class ErrorMessage:
    wrong_code = "❗️ Resource returned HTTP {} code. Maybe link is broken"
    downloading = "⚠️ Unable to download file"
    converting_webm = "⚠️ Sorry, <code>ffmpeg</code> seems unable to convert this file to MP4. Please, contact @Mike_Went"
    converting_webp = "⚠️ Sorry, <code>ffmpeg</code> seems unable to convert this file to JPG. Please, contact @Mike_Went"
    generating_thumbnail = "⚠️ Sorry, <code>ffmpeg</code> seems unable to generate a thumbnail image for this file. Please, contact @Mike_Went"
    huge_file = "🍉 File is bigger than 50 MB. Telegram <b>does not<b> allow me to upload huge files, sorry."
    no_header_webm = "🔬 WTF? I do not understand what server tries to give me instead of .webm file"
    no_header_webp = "🔬 WTF? I do not understand what server tries to give me instead of .webp file"
    file_not_webm = "👀 This is not a .webm file. If you are sure it's an error, contact @Mike_Went"
    file_not_webp = "👀 This is not a .webp file. If you are sure it's an error, contact @Mike_Went"
    file_not_supported = "👀 This file is not supported. Supported files are: webm, webp. If you are sure it's an error, contact @Mike_Went"


config = {}
try:
    with open("config.json", "r") as f:
        config = json.load(f)
except FileNotFoundError:
    with open("config.json", "w") as f:
        config = {"telegram_token": None, "ffmpeg_threads": 2, "temp_path": "/tmp/"}
        json.dump(config, f, indent=4)
except:
    print("Unable to parse config.json, is it corrupted?")
    exit(1)

if not config.get("telegram_token"):
    print("Please specify Telegram bot token in config.json")
    exit(1)


def update_status_message(message, text):
    try:
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message.message_id,
            text=text,
            parse_mode="HTML",
        )
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
    return "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(length)
    )


def convert_worker(target_format, message, url, config, bot):
    """Generic process spawned every time user sends a link or a file"""
    filename = "".join([config["temp_path"], random_string(), "." + target_format])

    # Tell user that we are working
    status_message = bot.reply_to(message, Message.starting, parse_mode="HTML")

    # Try to download URL
    try:
        r = requests.get(url, stream=True)
    except:
        update_status_message(status_message, ErrorMessage.downloading)
        return

    # Something went wrong on the server side
    if r.status_code != 200:
        update_status_message(status_message, ErrorMessage.wrong_code.format(r.status_code))
        return

    # Is it a webm/webp file?
    if (
        r.headers["Content-Type"] not in ALLOWED_MIME_TYPES_VIDEO
        and message.document.mime_type not in ALLOWED_MIME_TYPES_VIDEO
    ):
        update_status_message(status_message, ErrorMessage.file_not_webm)
        return

    # Can't determine file size
    if not "Content-Length" in r.headers or not "Content-Type" in r.headers:
        update_status_message(status_message, ErrorMessage.no_header_webm)
        return

    # Check file size
    if int(r.headers["Content-Length"]) >= MAXIMUM_FILESIZE_ALLOWED:
        update_status_message(status_message, ErrorMessage.huge_file)
        return

    # Start ffmpeg
    ffmpeg_process = None
    if target_format == "mp4":
        ffmpeg_process = subprocess.Popen(
            [
                "ffmpeg", "-v", "error",
                "-threads", str(config["ffmpeg_threads"]),
                "-i", url,
                "-map", "V:0?",                          # select video stream
                "-map", "0:a?",                          # ignore audio if doesn't exist
                "-c:v", "libx264",                       # specify video encoder
                "-max_muxing_queue_size", "9999",        # https://trac.ffmpeg.org/ticket/6375
                "-movflags", "+faststart",               # optimize for streaming
                "-preset", "veryslow",                   # https://trac.ffmpeg.org/wiki/Encode/H.264#a2.Chooseapresetandtune
                "-timelimit", "900",                     # prevent DoS (exit after 15 min)
                "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",  # https://stackoverflow.com/questions/20847674/ffmpeg-libx264-height-not-divisible-by-2#20848224
                filename,
            ]
        )
    elif target_format == "jpg":
        ffmpeg_process = subprocess.Popen(
            [
                "ffmpeg", "-v", "error",
                "-threads", str(config["ffmpeg_threads"]),
                "-thread_type", "slice",
                "-i", url,                # allow ffmpeg to download image by it url
                "-timelimit", "60",       # prevent DoS (exit after 15 min)
                filename,
            ]
        )

    # While ffmpeg process is alive (i.e. is working)
    old_progress = ""
    while not ffmpeg_process.poll():
        try:
            raw_output_size = os.stat(filename).st_size
        except FileNotFoundError:
            raw_output_size = 0

        output_size = size(raw_output_size, system=alternative)
        input_size = size(int(r.headers["Content-Length"]), system=alternative)

        human_readable_progress = " ".join([output_size, "/", input_size])
        # Update progress only if it changed
        if human_readable_progress != old_progress:
            update_status_message(
                status_message, Message.converting.format(human_readable_progress)
            )
            old_progress = human_readable_progress
        time.sleep(3)

    # Exit in case of error with ffmpeg
    if ffmpeg_process.returncode != 0:
        update_status_message(status_message, ErrorMessage.converting_webm)
        # Clean up and close pipe explicitly
        rm(filename)
        return

    # Check output file size
    output_size = os.path.getsize(filename)
    if output_size >= MAXIMUM_FILESIZE_ALLOWED:
        update_status_message(status_message, ErrorMessage.huge_file)
        # Clean up and close pipe explicitly
        rm(filename)
        return

    # Default params for sending operation
    filelist = []
    data = {
        "chat_id": message.chat.id,
        "reply_to_message_id": message.message_id,
        "supports_streaming": True,
    }

    if target_format == "mp4":
        # 1. Get video duration in seconds
        video_duration = (
            subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    filename,
                ],
                stdout=subprocess.PIPE,
            )
            .stdout.decode("utf-8")
            .strip()
        )
        video_duration = round(float(video_duration))
        data.update({"duration": video_duration})

        # 2. Get video height and width
        video_props = (
            subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height",
                    "-of", "csv=s=x:p=0",
                    filename,
                ],
                stdout=subprocess.PIPE,
            )
            .stdout.decode("utf-8")
            .strip()
        )
        video_width, video_height = video_props.split("x")
        data.update({"width": video_width, "height": video_height})

        # 3. Take one frame from the middle of the video
        update_status_message(status_message, Message.generating_thumbnail)
        thumbnail = "".join([config["temp_path"], random_string(), ".jpg"])
        generate_thumbnail_process = subprocess.Popen(
            [
                "ffmpeg", "-v", "error",
                "-i", filename,
                "-vcodec", "mjpeg",
                "-vframes", "1",
                "-an",
                "-f", "rawvideo",
                "-ss", str(int(video_duration / 2)),
                # keep the limit of 90px height/width (Telegram API) while preserving the aspect ratio
                "-vf", "scale='if(gt(iw,ih),90,trunc(oh*a/2)*2)':'if(gt(iw,ih),trunc(ow/a/2)*2,90)'",
                thumbnail,
            ]
        )

        # While process is alive (i.e. is working)
        while generate_thumbnail_process.poll() == None:
            time.sleep(1)

        # Exit in case of error with ffmpeg
        if generate_thumbnail_process.returncode != 0:
            update_status_message(status_message, ErrorMessage.generating_thumbnail)
            return

        filelist = [
            ("video", (random_string() + ".mp4", open(filename, "rb"), "video/mp4")),
            ("thumb", (random_string() + ".jpg", open(thumbnail, "rb"), "image/jpeg")),
        ]
    elif target_format == "jpg":
        filelist = [
            ("photo", (random_string() + ".jpg", open(filename, "rb"), "image/jpeg"))
        ]

    # Upload to Telegram
    update_status_message(status_message, Message.uploading)
    requests.post(
        "https://api.telegram.org/bot{}/sendVideo".format(config["telegram_token"]),
        data=data,
        files=filelist,
    )
    bot.delete_message(message.chat.id, status_message.message_id)


### Telegram interaction below ###
def report_unsupported_file(message):
    if message.chat.type == "private":
        bot.reply_to(message, ErrorMessage.file_not_supported, parse_mode="HTML")


telegram_token = config["telegram_token"]
bot = telebot.TeleBot(telegram_token)


@bot.message_handler(commands=["start", "help"])
def start_help(message):
    bot.send_message(message.chat.id, Message.start, parse_mode="HTML")
    bot.send_message(message.chat.id, Message.help, parse_mode="HTML")


# Handle URLs
URL_REGEXP = r"(http.?:\/\/.*\.(webm|webp|mp4))"
@bot.message_handler(regexp=URL_REGEXP)
def handle_urls(message):
    # Grab first found link
    try:
        match = re.findall(URL_REGEXP, message.text)[0]
        url = match[0]
        extension = match[1]
    except:
        report_unsupported_file(message)
        return

    if extension in ("webm", "mp4"):
        target_format = "mp4"
    elif extension == "webp":
        target_format = "jpg"
    else:
        report_unsupported_file(message)
        return

    threading.Thread(
        target=convert_worker,
        kwargs={
            "target_format": target_format,
            "message": message,
            "url": url,
            "config": config,
            "bot": bot,
        },
    ).start()


# Handle files
@bot.message_handler(content_types=["document", "video"])
def handle_files(message):
    file_info = bot.get_file(message.document.file_id if message.document.file_id else message.video.file_id)
    if (
        message.document.mime_type not in ALLOWED_MIME_TYPES_VIDEO
        and message.document.mime_type not in ALLOWED_MIME_TYPES_IMAGE
    ):
        report_unsupported_file(message)
        return

    url = "https://api.telegram.org/file/bot{0}/{1}".format(
        telegram_token, file_info.file_path
    )

    if url.endswith("webm") or url.endswith("mp4"):
        target_format = "mp4"
    elif url.endswith("webp"):
        target_format = "jpg"
    else:
        report_unsupported_file(message)
        return

    threading.Thread(
        target=convert_worker,
        kwargs={
            "target_format": target_format,
            "message": message,
            "url": url,
            "config": config,
            "bot": bot,
        },
    ).start()


bot.polling(none_stop=True)
