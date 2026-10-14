# RiiTube

Watch YouTube, Dailymotion and Vimeo on your Wii with [WiiMC](https://wiimc.org/).

RiiTube is a small Flask app that:

1. Searches YouTube (or lists popular and trending videos) with yt-dlp and returns a playlist in WiiMC's format.
2. Downloads the chosen video with yt-dlp and streams it to the Wii.

## Endpoints

| Path | Purpose |
| --- | --- |
| `/onlinemedia.xml` | WiiMC online media menu (YouTube, Dailymotion, Vimeo, radio) |
| `/wiimc/` | Most popular videos (M3U) |
| `/wiimc/?trending=1` | Trending videos (M3U) |
| `/wiimc/?q=<query>&page=<n>` | YouTube search (PLX, paginated) |
| `/video/wii/?q=<id>&site=<youtube\|dailymotion\|vimeo>` | Streams the video |

Search results include **Next page**, **Previous page** and **New search** entries. They use WiiMC's PLX format so page links open as playlists while videos stay playable with thumbnails. YouTube gives no total page count, so a nonempty page offers the next one, and an empty page lets you go back or start a new search. A failed page can be retried in place. Video IDs are validated before they reach playback and thumbnail URLs.

## Setup

```bash
pip install -r requirements.txt
# optionally create a .env with the settings below
./run.sh
```

`run.sh` starts the server with waitress on `PORT` (default `5001`). The app writes logs to `/root/logs/app.log`, so that directory must exist.

YouTube has tightened its bot checks, so a datacenter server needs a few extras:

1. **A proxy** (optional). Set `WINDSCRIBE_USERNAME` and `WINDSCRIBE_PASSWORD` to route yt-dlp through a Windscribe HTTPS proxy. `WINDSCRIBE_SERVER` pins a host instead of picking a healthy one.
2. **A PO token provider.** `requirements.txt` installs the bgutil yt-dlp plugin, but the matching [bgutil HTTP server](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) must also run. The app starts it with Deno from `/root/projects/bgutil-ytdlp-pot-provider` when Deno is installed. `POT_PROVIDER_URL` (default `http://127.0.0.1:4416`) is the server's base address, passed to yt-dlp as `youtubepot-bgutilhttp:base_url`.
3. **A JavaScript runtime** such as Deno, which yt-dlp needs for YouTube ([details](https://github.com/yt-dlp/yt-dlp/wiki/EJS)).
4. **Cookies** (last resort). Public videos usually don't need them, so the shared YouTube cookie file is only used on the final retry. Playwright refreshes it every 12 hours, so run `playwright install chromium` once.

If a video fails, check the yt-dlp log lines in `app.log` for provider loading, token generation and runtime availability before changing authentication.

## Configuration

Set these in `.env` or the environment.

| Variable | Default | Meaning |
| --- | --- | --- |
| `PORT` | `5001` | Port to listen on |
| `SENTRY_DSN` | unset | Enables Sentry error reporting |
| `POT_PROVIDER_URL` | `http://127.0.0.1:4416` | bgutil server base address |
| `COOKIE_FILE`, `COOKIE_FILE_DAILYMOTION`, `COOKIE_FILE_VIMEO` | `cookie*.txt` | Netscape cookie files |
| `YOUTUBE_MAX_CONCURRENT` | `4` | Simultaneous YouTube downloads |
| `YOUTUBE_MAX_RETRIES` | `3` | Attempts per YouTube video |
| `SLOT_WAIT_SECONDS` | `25` | How long a request waits for a free download slot |
| `FIRST_BYTE_SECONDS` | `60` | Kill a download that sends no data in this time |
| `MAX_STREAM_SECONDS` | `900` | Hard cap on a single stream |
| `FAIL_CACHE_SECONDS` | `45` | Refuse a video that just failed, so the Wii's automatic retries don't burn download slots |
| `FAST_FIRST_ATTEMPT` | off | Set to `1` to skip yt-dlp's pre-roll ad wait on the first try (experimental) |

## Stream handling

Each download runs in its own process group. When the Wii disconnects, or a stream stalls past `FIRST_BYTE_SECONDS` or `MAX_STREAM_SECONDS`, the group (yt-dlp and its ffmpeg) gets SIGTERM, then SIGKILL after five seconds, and is reaped so nothing keeps downloading. Live broadcasts are rejected so they can't hold a slot forever.

## License

GPL-3.0, see [LICENSE](LICENSE).
