#!/usr/bin/env python3
from cgi import FieldStorage
import atexit
import os
import vimeo


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

os.environ['HTTP_PROXY'] = "http://localhost:8888"
os.environ['HTTPS_PROXY'] = "http://localhost:8888"

v = vimeo.VimeoClient(
    token="b0acb6b53986ddef2c2cb4417c627bce",
    key="57495f1cd3af69fc968bbf6df62eebc9fe4a3063",
    secret="NCCiDI8jX8h8sXX21drIl/00AGXKCUKO6il8mOqyZvgV7bvsgs4fTLzeSqPt0u+BoIns1ZDV6V2KtzPffyGTjS6DpepE5g/RBcAKKsDChnPyErNrpcT9FbfFnB1i6Jk9"
)

form = FieldStorage()

api = v.get('/videos', params={"query": form["q"].value, "per_page": 50}).json()["data"]

print("Content-Type: text/plain;charset=UTF-8;\n");

print("#EXTM3U")

i = 1

for entry in api:
    print("#EXTINF:-1," + entry["name"])
    print("http://riitube.rc24.xyz/video/wii/?site=vimeo&q=" + entry["link"].replace("https://vimeo.com/", ""))

    i += 1
