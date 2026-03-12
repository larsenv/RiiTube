#!/usr/bin/env python3
from sys import stdout
from cgi import FieldStorage
import requests
import json
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

if "q" in form.keys():
    api = requests.get("http://95.217.72.119:29864/api/v1/search?q=" + form["q"].value).json()
elif "trending" in form.keys():
    api = requests.get("http://95.217.72.119:29864/api/v1/trending").json()
else:
    api = requests.get("http://95.217.72.119:29864/api/v1/popular").json()

print("Content-Type: text/plain;charset=UTF-8;\n");

print("#EXTM3U")

i = 1

for entry in api:
    try:
        print("#EXTINF:-1=" + '"' + "http://i.ytimg.com/vi/" + entry["videoId"] + "/mqdefault.jpg" + '"' + "," + entry["title"])
        print("http://riitube.rc24.xyz/video/wii/?q=" + entry["videoId"])

        i += 1
    except:
        continue
