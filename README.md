# RiiTube
A way to watch YouTube on your Wii with WiiMC.

The code is extremely simple. All it does is:

1. For YouTube, uses Inviduous API to search for videos, or browse trending or popular videos (probably tech-related because that's what Inviduous tends to grab). Or uses the Vimeo or Dailymotion API.
2. Returns a playlist file in WiiMC format.
3. Uses yt-dlp to download video file, and proxies that to the Wii.

NOTE: Since YouTube increased their security, there are some prereqesites to this code. As I run this on my own server and not a residential IP, I made changes to the script. It expect

1. A VPN proxy
2. A Individous instance self hosted
3. A PO Token generator
4. Cookie exported off YouTube
