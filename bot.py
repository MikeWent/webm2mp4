#!/usr/bin/env python3

# https://github.com/MikeWent/webm2mp4
# https://t.me/webm2mp4bot

import subprocess
import threading
import string
import random
import time
import os
# external modules
import requests
import telebot

# SETTINGS
TOKEN = ''
TEMP_FOLDER = '/tmp/'
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.91 Safari/537.36 Viv/1.92.917.39',
           # for real size in headers
           'Accept-Encoding': 'identity'}

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

def get_commmand_args(message_text):
    """Get telegram command arguments. Example: 'args' in '/command args'"""
    return ''.join([x+' ' for x in message_text.split(' ')[1:]])

def update_status_message(message, text):
    bot.edit_message_text(chat_id = message.chat.id,
                          message_id = message.message_id,
                          text = text, parse_mode='HTML')

def rm(filename):
    try:
        os.remove(filename)
    except:
        pass

def webm2mp4_worker(message):
    # check url
    url = message.text if not message.text[0] == '/' else get_commmand_args(message.text).strip()
    if url == '':
        bot.reply_to(message, message_help, parse_mode='HTML')
        return
    elif not url.endswith('.webm'):
        bot.reply_to(message, error_wrong_url, parse_mode='HTML')
        return
    # generate temp filename
    temp_filename = TEMP_FOLDER + ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    # tell user that we are working
    status_message = bot.reply_to(message, message_processing, parse_mode='HTML')
    try:
        r = requests.get(url, stream=True, headers=HEADERS)
    except:
        update_status_message(status_message, error_downloading)
        return
    if r.status_code == 200:
        if not 'Content-Length' in r.headers or not 'Content-Type' in r.headers:
            update_status_message(status_message, error_no_header)
            return
        if r.headers['Content-Type'] != 'video/webm':
            update_status_message(status_message, error_file_not_webm)
            return
        # check file size
        webm_size = int(r.headers['Content-Length'])
        if webm_size >= 52428800:
             update_status_message(status_message, error_huge_file)
             return
        update_status_message(status_message, message_downloading)
        # buffered download
        with open(temp_filename+'.webm', 'wb') as f:
            for chunk in r:
                f.write(chunk)
    else:
        # somethig went worng on the server-side
        update_status_message(status_message, error_wrong_code.format(r.status_code))
        # cleanup
        rm(temp_filename+'.webm')
        return
    # start converting
    ffmpeg_process = subprocess.Popen(["ffmpeg", "-loglevel", "fatal", "-i", temp_filename+".webm", temp_filename+".mp4"])
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
    mp4_size = os.path.getsize(temp_filename+'.mp4')
    if mp4_size >= 52428800: # ~50 MB
        update_status_message(status_message, error_huge_file)
        return
    # upload
    update_status_message(status_message, message_uploading)
    mp4 = open(temp_filename+'.mp4', 'rb')
    bot.send_video(message.chat.id, mp4, reply_to_message_id=message.message_id)
    bot.delete_message(message.chat.id, status_message.message_id)
    # cleanup
    rm(temp_filename+'.webm')
    rm(temp_filename+'.mp4')

### Telegram interaction below ###
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start_help(message):
    bot.reply_to(message, message_start, parse_mode='HTML')

@bot.message_handler(commands=['webm'])
def webm2mp4(message):
    new_worker = threading.Thread(target=webm2mp4_worker, kwargs={"message": message})
    new_worker.start()
    return

# also handle messages with just .webm in the end
@bot.message_handler(func=lambda message: message.text.endswith('.webm') if message.text else False)
def symlink(message):
    webm2mp4(message)

bot.polling(none_stop=True, interval=3)
