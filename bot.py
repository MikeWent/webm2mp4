#!/usr/bin/env python3

# https://github.com/MikeWent/webm2mp4
# https://t.me/webm2mp4bot

import re
import subprocess
import time
import threading

import requests
import telebot

import utils
import text

MAXIMUM_FILESIZE_ALLOWED = 50 * 1024 * 1024  # ~50 MB
config = utils.load_config("config.json")
if config.get("telegram_token") == "":
    print(f"Please specify Telegram bot token in config.json")
    exit(1)

def convert_worker(target_format, message, url, config, bot):
    """Generic process spawned every time user sends a link or a file"""
    input_filename = "".join([config["temp_path"], utils.random_string()])
    output_filename = "".join([config["temp_path"], utils.random_string(), ".", target_format])

    # Tell user that we are working
    status_message = bot.reply_to(message, text.starting, parse_mode="HTML")
    def update_status_message(new_text):
        bot.edit_message_text(chat_id=status_message.chat.id,
                              message_id=status_message.message_id,
                              text=new_text,
                              parse_mode="HTML")

    # Try to download URL
    try:
        r = requests.get(url, stream=True)
    except:
        update_status_message(text.error.downloading)
        return

    # Check file size
    if int(r.headers.get("Content-Length", "0")) >= MAXIMUM_FILESIZE_ALLOWED:
        update_status_message(text.error.huge_file)
        return

    # Download the file
    update_status_message(text.downloading)
    chunk_size = 4096
    raw_input_size = 0
    try:
        with open(input_filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                f.write(chunk)
                raw_input_size += chunk_size
                # Download files without Content-Length, but apply standard limit to them
                if raw_input_size >= MAXIMUM_FILESIZE_ALLOWED:
                    update_status_message(text.error.huge_file)
                    utils.rm(input_filename)
                    return
    except:
        update_status_message(text.error.downloading)
        bot.reply_to(message, f"HTTP {r.status_code}")
        return

    # Start ffmpeg
    ffmpeg_process = None
    if target_format == "mp4":
        ffmpeg_process = subprocess.Popen(
            [
                "ffmpeg", "-v", "error",
                "-threads", str(config["ffmpeg_threads"]),
                "-i", input_filename,
                "-map", "V:0?",                          # select video stream
                "-map", "0:a?",                          # ignore audio if doesn't exist
                "-c:v", "libx264",                       # specify video encoder
                "-max_muxing_queue_size", "9999",        # https://trac.ffmpeg.org/ticket/6375
                "-movflags", "+faststart",               # optimize for streaming
                "-preset", "veryslow",                   # https://trac.ffmpeg.org/wiki/Encode/H.264#a2.Chooseapresetandtune
                "-timelimit", "900",                     # prevent DoS (exit after 15 min)
                "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",  # https://stackoverflow.com/questions/20847674/ffmpeg-libx264-height-not-divisible-by-2#20848224
                output_filename,
            ]
        )
    elif target_format == "png":
        ffmpeg_process = subprocess.Popen(
            [
                "ffmpeg", "-v", "error",
                "-threads", str(config["ffmpeg_threads"]),
                "-thread_type", "slice",
                "-i", input_filename,
                "-timelimit", "60",       # prevent DoS (exit after 15 min)
                output_filename,
            ]
        )

    # Update progress while ffmpeg is alive
    old_progress = ""
    while ffmpeg_process.poll() == None:
        try:
            raw_output_size =  utils.filesize(output_filename)
        except FileNotFoundError:
            raw_output_size = 0

        if raw_output_size >= MAXIMUM_FILESIZE_ALLOWED:
            update_status_message(text.error.huge_file)
            ffmpeg_process.kill()
            utils.rm(output_filename)

        input_size = utils.bytes2human(raw_input_size)
        output_size = utils.bytes2human(raw_output_size)

        progress = f"{output_size} / {input_size}"
        # Update progress only if it changed
        if progress != old_progress:
            update_status_message(text.converting.format(progress))
            old_progress = progress
        time.sleep(2)

    # Exit in case of error with ffmpeg
    if ffmpeg_process.returncode != 0:
        update_status_message(text.error.converting)
        # Clean up and close pipe explicitly
        utils.rm(output_filename)
        return

    # Check output file size
    output_size = utils.filesize(output_filename)
    if output_size >= MAXIMUM_FILESIZE_ALLOWED:
        update_status_message(text.error.huge_file)
        # Clean up and close pipe explicitly
        utils.rm(output_filename)
        return

    # Default params for sending operation
    data = {
        "chat_id": message.chat.id,
        "reply_to_message_id": message.message_id
    }

    if target_format == "mp4":
        data.update({"supports_streaming": True})
        # 1. Get video duration in seconds
        video_duration = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                output_filename,
            ],
            stdout=subprocess.PIPE,
        ).stdout.decode("utf-8").strip()

        video_duration = round(float(video_duration))
        data.update({"duration": video_duration})

        # 2. Get video height and width
        video_props = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                output_filename,
            ],
            stdout=subprocess.PIPE,
        ).stdout.decode("utf-8").strip()

        video_width, video_height = video_props.split("x")
        data.update({"width": video_width, "height": video_height})

        # 3. Take one frame from the middle of the video
        update_status_message(text.generating_thumbnail)
        thumbnail = "".join([config["temp_path"], utils.random_string(), ".jpg"])
        generate_thumbnail_process = subprocess.Popen(
            [
                "ffmpeg", "-v", "error",
                "-i", output_filename,
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
            update_status_message(text.error.generating_thumbnail)
            return

        update_status_message(text.uploading)
        requests.post(
            "https://api.telegram.org/bot{}/sendVideo".format(config["telegram_token"]),
            data=data,
            files=[
                ("video", (utils.random_string() + ".mp4", open(output_filename, "rb"), "video/mp4")),
                ("thumb", (utils.random_string() + ".jpg", open(thumbnail, "rb"), "image/jpeg")),
            ],
        )
        utils.rm(output_filename)
        utils.rm(thumbnail)

    elif target_format == "png":
        # Upload to Telegram
        update_status_message(text.uploading)
        requests.post(
            "https://api.telegram.org/bot{}/sendPhoto".format(config["telegram_token"]),
            data=data,
            files=[("photo", (utils.random_string() + ".png", open(output_filename, "rb"), "image/png"))],
        )
        requests.post(
            "https://api.telegram.org/bot{}/sendDocument".format(config["telegram_token"]),
            data=data,
            files=[("document", (utils.random_string() + ".png", open(output_filename, "rb"), "image/png"))],
        )
        utils.rm(output_filename)
        
    bot.delete_message(message.chat.id, status_message.message_id)


telegram_token = config["telegram_token"]
bot = telebot.TeleBot(telegram_token)

@bot.message_handler(commands=["start", "help"])
def start_help(message):
    if message.chat.type != "private":
        try:
            bot.leave_chat(message.chat.id)
        except:
            pass
        return

    bot.send_message(message.chat.id, text.start, parse_mode="HTML")
    bot.send_message(message.chat.id, text.help, parse_mode="HTML")

# Handle URLs
URL_REGEXP = r"(http.?:\/\/.*\.(webm|webp|mp4))"
@bot.message_handler(regexp=URL_REGEXP)
def handle_urls(message):
    if message.chat.type != "private":
        try:
            bot.leave_chat(message.chat.id)
        except:
            pass
        return

    # Get first url in message
    match = re.findall(URL_REGEXP, message.text)[0]
    url = match[0]
    extension = match[1]
    if extension == "webp":
        target_format = "png"
    else:
        target_format = "mp4"

    threading.Thread(target=convert_worker, kwargs={"target_format": target_format, "message": message, "url": url, "config": config, "bot": bot}).run()

# Handle files
@bot.message_handler(content_types=["document", "video", "sticker"])
def handle_files(message):
    if message.chat.type != "private":
        try:
            bot.leave_chat(message.chat.id)
        except:
            pass
        return

    # Get file url
    target = None
    if message.document:
        target = message.document.file_id
    if message.video:
        target = message.video.file_id
    if message.sticker:
        # Ignore animated stickers
        if message.sticker.is_animated:
            bot.reply_to(message, text.error.animated_sticker, parse_mode="HTML")
            return
        target = message.sticker.file_id

    url = "https://api.telegram.org/file/bot{0}/{1}".format(telegram_token, bot.get_file(target).file_path)
    if url.endswith("webp"):
        target_format = "png"
    else:
        target_format = "mp4"

    threading.Thread(target=convert_worker, kwargs={"target_format": target_format, "message": message, "url": url, "config": config, "bot": bot}).run()


bot.polling(none_stop=True)
