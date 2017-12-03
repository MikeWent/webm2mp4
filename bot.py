#!/usr/bin/env python3

# https://github.com/MikeWent/webm2mp4
# https://t.me/webm2mp4bot

import string
import random
import os
# external modules
import ffmpy
import requests
import telebot

# SETTINGS
TOKEN = ''
TEMP_FOLDER = '/tmp/'
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.91 Safari/537.36 Viv/1.92.917.39',
           # for real size in headers
           'Accept-Encoding': 'identity'} 

# MESSAGES
errorWrongCode = 'Resource returned HTTP {} code. Check link or try again later :c'
errorDownloading = 'Unable to download file'
errorConverting = 'Unable to convert file to MP4'
errorWrongURL = 'This URL does not look like a .webm file'
errorHugeFile = 'File is bigger than 50 MB. Telegram does not allow to send huge files.'
errorNoHeader = 'WTF? I do not understand what server tries to give me instead of .webm file'
errorNotWebm = 'This is not a .webm'

messageWebmSyntax = 'Syntax: <code>/webm http://host.com/video.webm</code>'
messageStart = 'Hello! I am webm to mp4 converter. Send me a <b>link to webm file</b>, I will convert it and upload mp4 to Telegram.\n\n'+messageWebmSyntax
messageProcessing = 'Processing...'
messageDownloading = 'Downloading file...'
messageConverting = 'Converting to MP4 (please be patient)...'
messageUploading = 'Uploading to Telegram...'

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

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start')
def start_help(message):
    bot.reply_to(message, messageStart, parse_mode='HTML')

@bot.message_handler(commands=['webm'])
def webm2mp4(message):
    url = message.text if not message.text[0] == '/' else get_commmand_args(message.text).strip()
    if url == '':
        bot.reply_to(message, messageWebmSyntax, parse_mode='HTML')
        return
    elif not url.endswith('.webm'):
        bot.reply_to(message, errorWrongURL, parse_mode='HTML')
        return
    
    # generate temp filename
    temp_filename = TEMP_FOLDER + ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    
    status_message = bot.reply_to(message, messageProcessing, parse_mode='HTML')
    try:
        r = requests.get(url, stream=True, headers=HEADERS)
    except:
        update_status_message(status_message, errorDownloading)
        return
    
    if r.status_code == 200:
        if not 'Content-Length' in r.headers or not 'Content-Type' in r.headers:
            update_status_message(status_message, errorNoHeader)
            return   
        if r.headers['Content-Type'] != 'video/webm':
            update_status_message(status_message, errorNotWebm)
            return
        
        webm_size = int(r.headers['Content-Length'])
        if webm_size >= 52428800:
             update_status_message(status_message, errorHugeFile)
             return
        # download
        update_status_message(status_message, messageDownloading)
        with open(temp_filename+'.webm', 'wb') as f:
            for chunk in r:
                f.write(chunk)
    else:
        update_status_message(status_message, errorWrongCode.format(r.status_code))
        rm(temp_filename+'.webm')
        return
    
    update_status_message(status_message, messageConverting)
    # start ffmpeg
    ff = ffmpy.FFmpeg(global_options='-loglevel panic',
        inputs={temp_filename+'.webm': None},
        outputs={temp_filename+'.mp4': '-strict -2'}
    )
    try:
        ff.run()
    except:
        update_status_message(status_message, errorConverting)
        rm(temp_filename+'.webm')
        rm(temp_filename+'.mp4')
        return
    
    mp4_size = os.path.getsize(temp_filename+'.mp4')
    if mp4_size >= 52428800:
        update_status_message(status_message, errorHugeFile)
        return
    
    update_status_message(status_message, messageUploading)
    bot.send_chat_action(chat_id=message.chat.id, action='upload_video')
    mp4 = open(temp_filename+'.mp4', 'rb')
    bot.send_video(message.chat.id, mp4, reply_to_message_id=message.message_id)
    bot.delete_message(message.chat.id, status_message.message_id)
    rm(temp_filename+'.webm')
    rm(temp_filename+'.mp4')

@bot.message_handler(func=lambda m: True)
def symlink(message):
    if message.text.endswith('.webm'):
        webm2mp4(message)

bot.polling(none_stop=True, interval=3)
