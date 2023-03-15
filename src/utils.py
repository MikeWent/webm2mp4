import json
import os
import random
import string

from hurry.filesize import alternative, size


def bytes2human(raw):
    return size(raw, system=alternative)

def filesize(filename):
    return os.stat(filename).st_size

def load_config(filename):
    # Default config
    config = {"telegram_token": "",
              "ffmpeg_threads": 2,
              "temp_path": "/tmp/"}
    try:
        with open(filename, "r") as f:
            config.update(json.load(f))
        return config
    except FileNotFoundError:
        with open(filename, "w") as f:
            json.dump(config, f, indent=4)
            return config
    except:
        print(f"Unable to parse {filename}, is it corrupted?")
        exit(1)


def rm(filename):
    """Delete file"""
    try:
        os.remove(filename)
    except Exception as e:
        print(f"Unable to rm {filename}: {e}")


def random_string(length=12):
    """Random string of uppercase ASCII and digits"""
    return "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(length)
    )

