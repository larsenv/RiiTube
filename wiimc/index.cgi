#!/usr/bin/env python3
from sys import stdout, stderr
from cgi import FieldStorage
import requests
import json

form = FieldStorage()

print("Content-Type: text/plain;charset=UTF-8;\n");
print("#EXTM3U")

try:
    if "q" in form:
        url = "http://95.217.72.119:29864/api/v1/search?q=" + form["q"].value
    elif "trending" in form:
        url = "http://95.217.72.119:29864/api/v1/trending"
    else:
        url = "http://95.217.72.119:29864/api/v1/popular"

    response = requests.get(url, timeout=10)
    response.raise_for_status()
    api = response.json()
except Exception as e:
    stderr.write(f"Error fetching API data from {url if 'url' in locals() else 'unknown'}: {e}\n")
    api = []

if not isinstance(api, list):
    stderr.write(f"Warning: API response is not a list: {type(api)}\n")
    if isinstance(api, dict) and "error" in api:
         stderr.write(f"API Error: {api['error']}\n")
    api = []

for entry in api:
    try:
        # Check if entry is a dictionary and has required keys
        if not isinstance(entry, dict) or "videoId" not in entry or "title" not in entry:
            continue
            
        print("#EXTINF:-1=" + '"' + "http://i.ytimg.com/vi/" + entry["videoId"] + "/mqdefault.jpg" + '"' + "," + entry["title"])
        print("http://riitube.rc24.xyz/video/wii/?q=" + entry["videoId"])
    except Exception as e:
        stderr.write(f"Error processing entry: {e}\n")
        continue
