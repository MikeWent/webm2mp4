FROM debian:11
RUN apt update && apt install -y --no-install-recommends python3 python3-pip ffmpeg
RUN adduser bot

COPY src /opt
COPY requirements.txt /opt
RUN pip3 install --upgrade -r /opt/requirements.txt

USER bot
WORKDIR /opt
ENTRYPOINT ["python3", "./bot.py"]
