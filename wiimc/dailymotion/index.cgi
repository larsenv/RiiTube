#!/usr/bin/env python3
from cgi import FieldStorage
import dailymotion
import threading


def _load_env(path="/opt/.env"):
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env[key.strip()] = val.strip().strip('"').strip("'")
    except Exception:
        pass
    return env


def _init_sentry():
    dsn = _load_env().get("SENTRY_DSN")
    if dsn:
        try:
            import sentry_sdk
            sentry_sdk.init(dsn=dsn, traces_sample_rate=0)
        except Exception:
            pass


threading.Thread(target=_init_sentry, daemon=True).start()

form = FieldStorage()

d = dailymotion.Dailymotion()

api = d.get('/videos', params={"search": form["q"].value, "limit": 50})["list"]

print("Content-Type: text/plain;charset=UTF-8;\n");

print("#EXTM3U")

i = 1

for entry in api:
    print("#EXTINF:-1," + entry["title"])
    print("http://riitube.rc24.xyz/video/wii/?site=dailymotion&q=" + entry["id"])

    i += 1
