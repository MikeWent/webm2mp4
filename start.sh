#!/bin/bash
cd $(dirname "$0")
DIR="$( cd "$( dirname "$0" )" && pwd )"
while true; do
	python3 -B $DIR/bot.py
	echo "start.sh: restarting in 1 sec"
	sleep 1
done
