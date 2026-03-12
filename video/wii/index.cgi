#!/usr/bin/env python3
from cgi import FieldStorage
from sys import stdout
import io
import requests
import subprocess
import threading
import urllib.parse


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

video_url = "http://youtube.com/watch?v=" + form["q"].value + "/"

try:
    if form["site"].value == "vimeo":
        video_url = "https://vimeo.com/" + form["q"].value
    elif form["site"].value == "dailymotion":
        video_url = "https://dailymotion.com/video/" + form["q"].value
except:
    pass

stdout.buffer.write(b"Content-Type:application/octet-stream\n\n")
stdout.flush()

if "youtube" in video_url:
    proc = subprocess.Popen(["/usr/local/bin/yt-dlp", "--remote-components", "ejs:github", "--proxy", "http://localhost:8888/", "--cookies", "/opt/`.txt", "--extractor-args", "youtube:pot_provider=http://127.0.0.1:4416/v1/token", "-f", "[width<=641]", video_url, "-o", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
elif "vimeo" in video_url:
    proc = subprocess.Popen(["/usr/local/bin/yt-dlp", "-f", "ba+bv[width<=641]", "--cookies", "/opt/7.txt", video_url, "-o", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
elif form["site"].value == "dailymotion":
    direct_url = subprocess.check_output(
        ['/usr/local/bin/yt-dlp', '--impersonate', 'chrome', '-f', 'best[width<=641]', '--get-url', video_url],
        text=True
    ).strip()
    proc = subprocess.Popen(["/bin/ffmpeg", "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5", "-i", direct_url, "-bsf:a", "aac_adtstoasc", "-c", "copy", "-movflags", "frag_keyframe+empty_moov", "-f", "mp4", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
processed = 0

for chunk in iter(proc.stdout):
    processed = 1
    stdout.flush()
    stdout.buffer.write(chunk)

if processed == 0:
    proc = subprocess.Popen(["/usr/local/bin/yt-dlp", "http://transfer.archivete.am/11UvgX/%60.mp4", "-o", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    for chunk1 in iter(proc.stdout):
        stdout.flush()
        stdout.buffer.write(chunk1)
