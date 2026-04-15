#!/usr/bin/env python3
from cgi import FieldStorage
from sys import stdout
import atexit
import io
import requests
import subprocess
import urllib.parse
import os
import signal


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


_sentry_dsn = _load_env().get("SENTRY_DSN")
if _sentry_dsn:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=_sentry_dsn, traces_sample_rate=0)
        atexit.register(lambda: sentry_sdk.flush(timeout=2))
    except Exception:
        pass

form = FieldStorage()

video_url = "http://youtube.com/watch?v=" + form.getvalue("q", "") + "/"

try:
    if form.getvalue("site") == "vimeo":
        video_url = "https://vimeo.com/" + form.getvalue("q", "")
    elif form.getvalue("site") == "dailymotion":
        video_url = "https://dailymotion.com/video/" + form.getvalue("q", "")
except:
    pass

stdout.buffer.write(b"Content-Type:application/octet-stream\n\n")
stdout.flush()

proc = None
processed = 0

try:
    if "youtube" in video_url:
        proc = subprocess.Popen(["/usr/local/bin/yt-dlp", "--remote-components", "ejs:github", "--proxy", "http://localhost:8888/", "--cookies", "/opt/`.txt", "--extractor-args", "youtube:pot_provider=http://127.0.0.1:4416/v1/token", "-f", "[width<=641]", video_url, "-o", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elif "vimeo" in video_url:
        proc = subprocess.Popen(["/usr/local/bin/yt-dlp", "-f", "ba+bv[width<=641]", "--cookies", "/opt/7.txt", video_url, "-o", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elif form.getvalue("site") == "dailymotion":
        direct_url = subprocess.check_output(
            ['/usr/local/bin/yt-dlp', '--impersonate', 'chrome', '-f', 'best[width<=641]', '--get-url', video_url],
            text=True
        ).strip()
        proc = subprocess.Popen(["/bin/ffmpeg", "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5", "-i", direct_url, "-bsf:a", "aac_adtstoasc", "-c", "copy", "-movflags", "frag_keyframe+empty_moov", "-f", "mp4", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    if proc:
        try:
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                stdout.buffer.write(chunk)
                stdout.flush()
                processed = 1
        except (BrokenPipeError, OSError):
            pass

    if processed == 0:
        if proc:
            proc.terminate()
            proc.wait()
        proc = subprocess.Popen(["/usr/local/bin/yt-dlp", "http://transfer.archivete.am/11UvgX/%60.mp4", "-o", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            while True:
                chunk1 = proc.stdout.read(65536)
                if not chunk1:
                    break
                stdout.buffer.write(chunk1)
                stdout.flush()
        except (BrokenPipeError, OSError):
            pass

finally:
    if proc:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
