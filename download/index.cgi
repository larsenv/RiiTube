#!/usr/bin/env python3
import atexit
import html
import os
import secrets
import subprocess
import urllib.parse
from cgi import FieldStorage
from sys import stdout


def load_env(path="/opt/.env"):
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


env = load_env()

sentry_dsn = env.get("SENTRY_DSN")
if sentry_dsn:
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=0)
        atexit.register(lambda: sentry_sdk.flush(timeout=2))
    except Exception:
        pass

PASSWORD = env.get("DOWNLOAD_PASSWORD", "")

_HTML_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Download</title>
<style>
  body {{ font-family: sans-serif; max-width: 480px; margin: 60px auto; padding: 0 16px; }}
  h1 {{ font-size: 1.4rem; }}
  label {{ display: block; margin-top: 12px; font-weight: bold; }}
  input[type=text], input[type=password] {{ width: 100%; box-sizing: border-box; padding: 8px; margin-top: 4px; }}
  button {{ margin-top: 16px; padding: 8px 20px; cursor: pointer; }}
  .error {{ color: #c00; margin-top: 12px; }}
</style>
</head>
<body>
<h1>Download YouTube Video</h1>
{error}
<form method="post">
  <label for="password">Password</label>
  <input type="password" id="password" name="password" autocomplete="current-password" required>
  <label for="url">YouTube URL</label>
  <input type="text" id="url" name="url" placeholder="https://www.youtube.com/watch?v=..." required>
  <button type="submit">Download</button>
</form>
</body>
</html>
"""


def send_html(error=""):
    error_html = (
        '<p class="error">' + html.escape(error) + "</p>" if error else ""
    )
    body = _HTML_PAGE.format(error=error_html).encode("utf-8")
    stdout.buffer.write(b"Content-Type: text/html; charset=UTF-8\n\n")
    stdout.buffer.write(body)
    stdout.flush()


def _is_youtube_url(url):
    try:
        parsed = urllib.parse.urlparse(url)
        return (
            parsed.scheme in ("http", "https")
            and parsed.netloc.lower().rstrip(".")
            in ("youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com")
        )
    except Exception:
        return False


method = os.environ.get("REQUEST_METHOD", "GET").upper()

if method != "POST":
    send_html()
else:
    form = FieldStorage()
    submitted_password = form.getvalue("password", "")
    video_url = form.getvalue("url", "").strip()

    if not PASSWORD or not secrets.compare_digest(submitted_password, PASSWORD):
        send_html(error="Incorrect password.")
    elif not video_url:
        send_html(error="Please provide a YouTube URL.")
    elif not _is_youtube_url(video_url):
        send_html(error="Only YouTube URLs are supported.")
    else:
        _YT_DLP = "/usr/local/bin/yt-dlp"
        _YT_DLP_ARGS = [
            "--remote-components", "ejs:github",
            "--proxy", "http://localhost:8888/",
            "--cookies", "/opt/`.txt",
            "--extractor-args", "youtube:pot_provider=http://127.0.0.1:4416/v1/token",
        ]

        # Single yt-dlp invocation: --print emits "title.ext\n" to stdout first,
        # then the binary video data follows immediately on the same pipe.
        # This avoids a separate metadata round-trip and starts the download right away.
        proc = subprocess.Popen(
            [_YT_DLP] + _YT_DLP_ARGS + ["--print", "%(title)s.%(ext)s", video_url, "-o", "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Read the filename line (--print emits "title.ext\n" before binary data)
        raw_name = proc.stdout.readline().decode("utf-8", errors="replace").strip()

        # Sanitise: strip chars that break headers or filesystems
        safe_name = "".join(
            c for c in raw_name if c not in r'\/:*?"<>|'
        ).strip()
        if not safe_name or "." not in safe_name:
            safe_name = "video.mp4"

        # RFC 5987 encoded filename for non-ASCII titles
        encoded_name = urllib.parse.quote(safe_name)
        ascii_name = safe_name.encode("ascii", "replace").decode().replace('"', "")

        stdout.buffer.write(b"Content-Type: application/octet-stream\n")
        stdout.buffer.write((
            'Content-Disposition: attachment; filename="' + ascii_name + '"; '
            "filename*=UTF-8''" + encoded_name + "\n\n"
        ).encode("utf-8"))
        stdout.flush()

        try:
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                stdout.buffer.write(chunk)
                stdout.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            proc.terminate()
            proc.wait()
