#!/usr/bin/env python3
from sys import stdout, stderr
from cgi import FieldStorage
import os
import vimeo

# Set proxy if needed
os.environ['HTTP_PROXY'] = "http://localhost:8888"
os.environ['HTTPS_PROXY'] = "http://localhost:8888"

form = FieldStorage()

print("Content-Type: text/plain;charset=UTF-8;\n");
print("#EXTM3U")

if "q" not in form:
    stderr.write("Error: Missing search query 'q'\n")
    exit(1)

try:
    v = vimeo.VimeoClient(
        token="b0acb6b53986ddef2c2cb4417c627bce",
        key="57495f1cd3af69fc968bbf6df62eebc9fe4a3063",
        secret="NCCiDI8jX8h8sXX21drIl/00AGXKCUKO6il8mOqyZvgV7bvsgs4fTLzeSqPt0u+BoIns1ZDV6V2KtzPffyGTjS6DpepE5g/RBcAKKsDChnPyErNrpcT9FbfFnB1i6Jk9"
    )

    response = v.get('/videos', params={"query": form["q"].value, "per_page": 50})
    api_data = response.json()
    api = api_data.get("data", [])
except Exception as e:
    stderr.write(f"Error fetching Vimeo data: {e}\n")
    api = []

if not isinstance(api, list):
    stderr.write(f"Warning: Vimeo API response 'data' is not a list: {type(api)}\n")
    api = []

for entry in api:
    try:
        if not isinstance(entry, dict) or "name" not in entry or "link" not in entry:
            continue
        print("#EXTINF:-1," + entry["name"])
        print("http://riitube.rc24.xyz/video/wii/?site=vimeo&q=" + entry["link"].replace("https://vimeo.com/", ""))
    except Exception as e:
        stderr.write(f"Error processing Vimeo entry: {e}\n")
        continue
