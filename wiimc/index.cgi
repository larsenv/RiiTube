#!/usr/bin/env python3
from sys import stdout, stderr
from cgi import FieldStorage
import requests
import json
import re
from urllib.parse import urlencode

form = FieldStorage()
searching = "q" in form
query = form.getfirst("q", "")
try:
    page = max(1, int(form.getfirst("page", "1")))
except ValueError:
    page = 1


def print_playlist_entry(kind, name, url, thumbnail=None):
    print()
    print("type=" + kind)
    print("name=" + " ".join(str(name).splitlines()))
    print("URL=" + url)
    if thumbnail:
        print("thumb=" + thumbnail)


def search_url(number):
    return "http://riitube.rc24.xyz/wiimc/?" + urlencode({"q": query, "page": number})

print("Content-Type: text/plain;charset=UTF-8;\n");
if searching:
    print("version=1")
    print("title=YouTube search - page " + str(page))
    if page > 1:
        print_playlist_entry(
            "playlist", "Previous page (" + str(page - 1) + ")", search_url(page - 1)
        )
else:
    print("#EXTM3U")

fetch_failed = False
try:
    if searching:
        url = "http://95.217.72.119:29864/api/v1/search?" + urlencode(
            {"q": query, "page": page, "type": "video"}
        )
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
    fetch_failed = True

if not isinstance(api, list):
    stderr.write(f"Warning: API response is not a list: {type(api)}\n")
    if isinstance(api, dict) and "error" in api:
         stderr.write(f"API Error: {api['error']}\n")
    api = []
    fetch_failed = True

for entry in api:
    try:
        # Check if entry is a dictionary and has required keys
        if not isinstance(entry, dict) or "videoId" not in entry or "title" not in entry:
            continue

        video_id = entry["videoId"]
        if not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            continue

        thumbnail = "http://i.ytimg.com/vi/" + video_id + "/mqdefault.jpg"
        video_url = "http://riitube.rc24.xyz/video/wii/?q=" + video_id
        if searching:
            print_playlist_entry("video", entry["title"], video_url, thumbnail)
        else:
            print("#EXTINF:-1=" + '"' + thumbnail + '"' + "," + entry["title"])
            print(video_url)
    except Exception as e:
        stderr.write(f"Error processing entry: {e}\n")
        continue

if searching:
    if fetch_failed:
        print_playlist_entry("playlist", "Search failed - select to retry", search_url(page))
    elif api:
        print_playlist_entry(
            "playlist", "Next page (" + str(page + 1) + ")", search_url(page + 1)
        )
    elif page > 1:
        print_playlist_entry("playlist", "No more results - back to first page", search_url(1))
    print_playlist_entry("search", "New search", "http://riitube.rc24.xyz/wiimc/?q=")
