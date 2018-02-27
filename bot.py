#!/usr/bin/env python3

# https://github.com/MikeWent/webm2mp4
# https://t.me/webm2mp4bot

import subprocess
import threading
import string
import random
import time
import os
import re
# external modules
import requests
import telebot

# SETTINGS
TOKEN = ''
TEMP_FOLDER = '/tmp/'
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.91 Safari/537.36 Viv/1.92.917.39',
           # for real size in headers
           'Accept-Encoding': 'identity'}
URL_REGEXP = r'(http.?:\/\/.*\.webm)'
MAXIMUM_FILESIZE_ALLOWED = 50*1024*1024 # ~50 MB

# MESSAGES
error_wrong_code = 'Resource returned HTTP {} code. Check link or try again later :c'
error_downloading = 'Unable to download file'
error_converting = 'Sorry, ffmpeg seems unable to convert this file to MP4'
error_wrong_url = 'This URL does not look like a .webm file'
error_huge_file = 'File is bigger than 50 MB. Telegram does not allow to send huge files.'
error_no_header = 'WTF? I do not understand what server tries to give me instead of .webm file'
error_file_not_webm = 'This is not a .webm'
message_help = 'Syntax: <code>/webm http://example.com/video.webm</code>'
message_start = 'Hello! I am webm to mp4 converter. Send me a <b>link to webm file</b>, I will convert it and upload mp4 to Telegram.\n\n'+message_help
message_processing = 'Processing...'
message_downloading = 'Downloading file...'
message_progress = 'Converting... {}'
message_uploading = 'Uploading to Telegram...'

def update_status_message(message, text):
    bot.edit_message_text(chat_id = message.chat.id,
                          message_id = message.message_id,
                          text = text, parse_mode='HTML')

def rm(filename):
    try:
        os.remove(filename)
    except:
        pass

def random_string(length=12):
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length))

def webm2mp4_worker(message, url):
    # generate temporary 12 symbols filename 
    filename = TEMP_FOLDER + random_string()
    # tell user that we are working
    status_message = bot.reply_to(message, message_processing, parse_mode='HTML')
    # try to download URL
    try:
        r = requests.get(url, stream=True, headers=HEADERS)
    except:
        update_status_message(status_message, error_downloading)
        return
    # somethig went worng on the server-side
    if r.status_code != 200:
        update_status_message(status_message, error_wrong_code.format(r.status_code))
        # cleanup
        rm(filename+'.webm')
        return
    # is it a webm file or not
    if r.headers['Content-Type'] != 'video/webm' and message.document.mime_type != 'video/webm':
        update_status_message(status_message, error_file_not_webm)
        return
    # can't determine file size
    if not 'Content-Length' in r.headers or not 'Content-Type' in r.headers:
        update_status_message(status_message, error_no_header)
        return
    # check file size
    webm_size = int(r.headers['Content-Length'])
    if webm_size >= MAXIMUM_FILESIZE_ALLOWED: 
        update_status_message(status_message, error_huge_file)
        return
    update_status_message(status_message, message_downloading)
    # buffered download
    try:
        with open(filename+'.webm', 'wb') as f:
            for chunk in r:
                f.write(chunk)
    except:
        update_status_message(status_message, error_downloading)

    # start converting
    ffmpeg_process = subprocess.Popen(["ffmpeg",
        "-i", filename+".webm",
        "-c:v",      "libx264",     # specify encoder
        "-movflags", "+faststart",  # optimize for streaming
        "-preset",   "slow",       # "speed / filesize"
        "-tune",     "fastdecode",
        filename+".mp4"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ffmpeg_process_pid = ffmpeg_process.pid
    while ffmpeg_process.poll() == None: # while ffmpeg process is working
        time.sleep(5)
        # get ffmpeg progress
        ffmpeg_progress = subprocess.run(["progress", "--quiet", "--pid", str(ffmpeg_process_pid)], stdout=subprocess.PIPE).stdout.decode("utf-8")
        if ffmpeg_progress == '':
            continue
        human_readable_progress = ffmpeg_progress.split("\n")[1].strip()
        update_status_message(status_message, message_progress.format(human_readable_progress))
    # exit if ffmpeg crashed
    if ffmpeg_process.returncode != 0:
        update_status_message(status_message, error_converting)
        return
    # check output file size
    mp4_size = os.path.getsize(filename+'.mp4')
    if mp4_size >= MAXIMUM_FILESIZE_ALLOWED:
        update_status_message(status_message, error_huge_file)
        return
    # upload
    update_status_message(status_message, message_uploading)
    mp4 = open(filename+'.mp4', 'rb')
    bot.send_video(message.chat.id, mp4, reply_to_message_id=message.message_id, supports_streaming=True)
    bot.delete_message(message.chat.id, status_message.message_id)
    # cleanup
    rm(filename+'.webm')
    rm(filename+'.mp4')

### Telegram interaction below ###
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start_help(message):
    bot.reply_to(message, message_start, parse_mode='HTML')

# handle URLs
@bot.message_handler(regexp=URL_REGEXP)
def handle_urls(message):
    # grab first found link
    url = re.findall(URL_REGEXP, message.text)[0]
    new_worker = threading.Thread(target=webm2mp4_worker, kwargs={"message": message, "url": url})
    new_worker.start()

# handle files
@bot.message_handler(content_types=['document'])
def handle_files(message):
    if message.document.mime_type != 'video/webm':
        return
    file_id = message.document.file_id
    file_info = bot.get_file(file_id)
    url = 'https://api.telegram.org/file/bot{0}/{1}'.format(TOKEN, file_info.file_path)
    new_worker = threading.Thread(target=webm2mp4_worker, kwargs={"message": message, "url": url})
    new_worker.start()

bot.polling(none_stop=True, interval=3)
