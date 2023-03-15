import os
import random
import string

from hurry.filesize import alternative, size


def bytes2human(raw):
    return size(raw, system=alternative)


def filesize(filename):
    return os.stat(filename).st_size


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
