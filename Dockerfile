FROM python:3-slim
RUN apt update -fy && apt install ffmpeg
RUN adduser -r bot

COPY src /opt
COPY requirements.txt /opt

USER bot
WORKDIR /opt
RUN pip3 install --user --upgrade -r requirements.txt

CMD ["python3", "./bot.py"]
