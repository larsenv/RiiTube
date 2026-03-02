#!/usr/bin/env python3
from cgi import FieldStorage
import dailymotion

form = FieldStorage()

d = dailymotion.Dailymotion()

api = d.get('/videos', params={"search": form["q"].value, "limit": 50})["list"]

print("Content-Type: text/plain;charset=UTF-8;\n");

print("#EXTM3U")

i = 1

for entry in api:
    print("#EXTINF:-1," + entry["title"])
    print("http://riitube.rc24.xyz/video/wii/?site=dailymotion&q=" + entry["id"])

    i += 1
