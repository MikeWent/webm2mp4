start = """Hello! I am WebM to MP4 (H.264) and WebP to PNG converter bot 📺

I can convert:
🎥 <b>webm</b> and other ffmpeg supported video format → mp4
🖼 <b>webp</b> and stickers → png & jpg"""
help = "Send me a <b>link</b> (http://...) or a <b>document</b> (including stickers)"
starting = "🚀 Starting..."
downloading = "📥 Downloading..."
converting = "☕️ Converting... {}"
generating_thumbnail = "🖼 Generating thumbnail.."
uploading = "☁️ Uploading to Telegram..."

class error:
    contact_hint = "Contat @Mike_Went if you think it's a bot-side error."

    downloading = "⚠️ Unable to download this file. " + contact_hint
    converting = "⚠️ Sorry, <code>ffmpeg</code> seems unable to convert this file. " + contact_hint
    generating_thumbnail = "⚠️ Sorry, <code>ffmpeg</code> seems unable to generate a thumbnail image for this file. " + contact_hint
    huge_file = "🍉 File is bigger than 50 MB. Telegram <b>does not<b> allow bots to upload huge files, sorry."
    animated_sticker = "🎬 Animated stickers are unsupported yet, submit a <a href='https://github.com/MikeWent/webm2mp4'>pull-request</a> if you implement it!"
