#!/usr/bin/env python3
from sys import stdout, stderr
from cgi import FieldStorage
import dailymotion

form = FieldStorage()

print("Content-Type: text/plain;charset=UTF-8;\n");
print("#EXTM3U")

if "q" not in form:
    stderr.write("Error: Missing search query 'q'\n")
    exit(1)

try:
    d = dailymotion.Dailymotion()
    api_response = d.get('/videos', params={"search": form["q"].value, "limit": 50})
    api = api_response.get("list", [])
except Exception as e:
    stderr.write(f"Error fetching Dailymotion data: {e}\n")
    api = []

if not isinstance(api, list):
    stderr.write(f"Warning: Dailymotion API response 'list' is not a list: {type(api)}\n")
    api = []

for entry in api:
    try:
        if not isinstance(entry, dict) or "id" not in entry or "title" not in entry:
            continue
        print("#EXTINF:-1," + entry["title"])
        print("http://riitube.rc24.xyz/video/wii/?site=dailymotion&q=" + entry["id"])
    except Exception as e:
        stderr.write(f"Error processing Dailymotion entry: {e}\n")
        continue
