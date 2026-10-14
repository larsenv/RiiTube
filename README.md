# RiiTube
A way to watch YouTube on your Wii with WiiMC.

The code is extremely simple. All it does is:

1. For YouTube, uses Inviduous API to search for videos, or browse trending or popular videos (probably tech-related because that's what Inviduous tends to grab). Or uses the Vimeo or Dailymotion API.
2. Returns a playlist file in WiiMC format.
3. Uses yt-dlp to download video file, and proxies that to the Wii.

YouTube searches include **Next page**, **Previous page**, and **New search** entries in WiiMC. Page links keep the original query and use Invidious's page parameter. Search results use WiiMC's PLX format so page links open as playlists while videos remain playable with thumbnails. Trending and popular lists continue to use M3U.

Invidious does not return a total page count. A nonempty API results page offers the next page, including when all entries on that page are skipped; an empty page has no next-page entry and lets you return to the previous page or start a new search. Failed API requests can be retried from the same page. Video IDs are validated before they are included in playback and thumbnail URLs.

NOTE: Since YouTube increased their security, there are some prereqesites to this code. As I run this on my own server and not a residential IP, I made changes to the script. It expect

1. A VPN proxy
2. A Individous instance
3. A PO Token generator
4. Cookie exported off YouTube

## YouTube runtime and token provider

Install `requirements.txt` into the Python environment used by
`/usr/local/bin/yt-dlp`. It includes the bgutil Python plugin; running the token
server alone does not install that plugin. Run the matching bgutil HTTP server
at `http://127.0.0.1:4416`. The CGI uses the plugin's `base_url` option, which takes
the server base address rather than a token endpoint. See the
[bgutil installation and verification guide](https://github.com/Brainicism/bgutil-ytdlp-pot-provider#installation).

Full YouTube support also needs a
[supported JavaScript runtime](https://github.com/yt-dlp/yt-dlp/wiki/EJS).
Deno is enabled by default; Node needs `--js-runtimes node` in yt-dlp's
configuration. `--remote-components ejs:github` supplies solver scripts, not the
runtime that executes them. Ensure the CGI service can find the runtime.

For public videos, account cookies are not always necessary. The proxy and
cookie arguments in this CGI are deployment-specific settings. yt-dlp documents
[request-rate limits and cookie requirements](https://github.com/yt-dlp/yt-dlp/wiki/Extractors),
and bgutil notes that tokens do not guarantee avoiding bot checks or HTTP 403
errors. Check verbose yt-dlp logs on the actual server for provider loading,
token generation, runtime availability, and the reported error before changing
authentication settings.
