#!/usr/bin/env python3
from cgi import FieldStorage
from sys import stdout, stderr
import subprocess

form = FieldStorage()

# Initial response headers
stdout.buffer.write(b"Content-Type:application/octet-stream\n\n")
stdout.flush()

if "q" not in form:
    # We already sent headers, so we can't send a 400 status easily in standard CGI
    # but we can just exit or send an error message if the client expects data.
    stderr.write("Error: Missing video ID 'q'\n")
    exit(1)

video_id = form["q"].value
site = form["site"].value if "site" in form else "youtube"

if site == "vimeo":
    video_url = "https://vimeo.com/" + video_id
elif site == "dailymotion":
    video_url = "https://dailymotion.com/video/" + video_id
else:
    video_url = "http://youtube.com/watch?v=" + video_id + "/"

proc = None
try:
    if "youtube" in video_url:
        proc = subprocess.Popen(["/usr/local/bin/yt-dlp", "--remote-components", "ejs:github", "--proxy", "http://localhost:8888/", "--cookies", "/opt/`.txt", "--extractor-args", "youtube:pot_provider=http://127.0.0.1:4416/v1/token", "-f", "[width<=641]", video_url, "-o", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elif "vimeo" in video_url:
        proc = subprocess.Popen(["/usr/local/bin/yt-dlp", "-f", "ba+bv[width<=641]", "--cookies", "/opt/7.txt", video_url, "-o", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elif site == "dailymotion":
        try:
            direct_url = subprocess.check_output(
                ['/usr/local/bin/yt-dlp', '--impersonate', 'chrome', '-f', 'best[width<=641]', '--get-url', video_url],
                text=True
            ).strip()
            proc = subprocess.Popen(["/bin/ffmpeg", "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5", "-i", direct_url, "-bsf:a", "aac_adtstoasc", "-c", "copy", "-movflags", "frag_keyframe+empty_moov", "-f", "mp4", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as e:
            stderr.write(f"Error getting dailymotion URL: {e}\n")
except Exception as e:
    stderr.write(f"Error starting subprocess: {e}\n")

processed = 0

if proc and proc.stdout:
    for chunk in iter(lambda: proc.stdout.read(8192), b''):
        processed = 1
        stdout.buffer.write(chunk)
        stdout.flush()

if processed == 0:
    stderr.write("Warning: Primary download failed, attempting fallback\n")
    try:
        proc = subprocess.Popen(["/usr/local/bin/yt-dlp", "http://transfer.archivete.am/11UvgX/%60.mp4", "-o", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.stdout:
            for chunk1 in iter(lambda: proc.stdout.read(8192), b''):
                stdout.buffer.write(chunk1)
                stdout.flush()
    except Exception as e:
        stderr.write(f"Error starting fallback subprocess: {e}\n")
