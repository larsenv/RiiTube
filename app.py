import os, re, signal, subprocess, urllib.parse, threading, time, asyncio, random, sys, logging, warnings
from flask import Flask, request, Response, stream_with_context
from dotenv import load_dotenv
import requests, sentry_sdk, yt_dlp
from sentry_sdk.integrations.flask import FlaskIntegration
import dailymotion, vimeo
from logging.handlers import RotatingFileHandler

# --- Logging ---
log_file = "/root/logs/app.log"
with open(log_file, "a") as f: pass
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s', 
                    handlers=[RotatingFileHandler(log_file, maxBytes=20*1024*1024, backupCount=3), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("RiiTube")
warnings.filterwarnings("ignore", category=UserWarning)
for name in ["pproxy", "asyncio", "urllib3", "waitress"]:
    logging.getLogger(name).setLevel(logging.ERROR)

# --- Configuration ---
load_dotenv(".env")
COOKIE_FILE = os.getenv("COOKIE_FILE", "cookieyoutube.txt")
COOKIE_FILE_DAILYMOTION = os.getenv("COOKIE_FILE_DAILYMOTION", "cookiedailymotion.txt")
COOKIE_FILE_VIMEO = os.getenv("COOKIE_FILE_VIMEO", "cookievimeo.txt")
POT_PROVIDER_URL = os.getenv("POT_PROVIDER_URL", "http://127.0.0.1:4416").rstrip("/")  # base address of the bgutil HTTP server, not a token endpoint
SEARCH_PAGE_SIZE = 20
VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
PORT = int(os.getenv("PORT", 5001))
YOUTUBE_MAX_CONCURRENT = max(1, int(os.getenv("YOUTUBE_MAX_CONCURRENT", 4)))
YOUTUBE_MAX_RETRIES = max(1, int(os.getenv("YOUTUBE_MAX_RETRIES", 3)))
MAX_STREAM_SECONDS = int(os.getenv("MAX_STREAM_SECONDS", 900))
FIRST_BYTE_SECONDS = int(os.getenv("FIRST_BYTE_SECONDS", 60))
SLOT_WAIT_SECONDS = int(os.getenv("SLOT_WAIT_SECONDS", 25))
FAIL_CACHE_SECONDS = int(os.getenv("FAIL_CACHE_SECONDS", 45))
FAST_FIRST_ATTEMPT = os.getenv("FAST_FIRST_ATTEMPT") == "1"  # experimental: 403s when the video needs the pre-roll ad wait
FAST_YTDLP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ytdlp_fast.py")

# Set NO_PROXY globally
os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1,10.126.200.241"

if os.getenv("SENTRY_DSN"):
    sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), integrations=[FlaskIntegration()], traces_sample_rate=0)

# --- Proxy ---
_cached_proxy_host = None
_cached_proxy_time = 0
_proxy_lock = threading.Lock()
_youtube_download_slots = threading.BoundedSemaphore(YOUTUBE_MAX_CONCURRENT)
# url -> expiry. A video that just failed every attempt is refused instantly instead of
# letting the Wii's automatic retries re-burn a download slot for ~30s each time.
_failed_urls = {}
_failed_lock = threading.Lock()
def _recently_failed(url):
    with _failed_lock:
        exp = _failed_urls.get(url)
        if exp and exp > time.time():
            return True
        _failed_urls.pop(url, None)
        if len(_failed_urls) > 500:
            now = time.time()
            for k in [k for k, v in _failed_urls.items() if v <= now]:
                _failed_urls.pop(k, None)
    return False

def get_proxy(force_refresh=False):
    global _cached_proxy_host, _cached_proxy_time
    user, pw = os.getenv("WINDSCRIBE_USERNAME"), os.getenv("WINDSCRIBE_PASSWORD")
    if not (user and pw): return None
    
    # Fallback hosts in case API call fails
    fallback_hosts = [
        "us-east-052.totallyacdn.com",
        "us-east-150.totallyacdn.com",
        "us-east-121.totallyacdn.com",
        "us-central-117.totallyacdn.com"
    ]
    with _proxy_lock:
        now = time.time()
        previous_server = _cached_proxy_host
        server = os.getenv("WINDSCRIBE_SERVER")

        if not server and previous_server and not force_refresh and (now - _cached_proxy_time < 600):
            server = previous_server
        elif not server:
            candidates = [host for host in fallback_hosts if host != previous_server] or fallback_hosts
            server = random.choice(candidates)
            try:
                # Fetch a healthy host. A retry explicitly excludes the host that just failed.
                resp = requests.get("https://assets.windscribe.com/serverlist/firefox/1/1", headers={"User-Agent": "Mozilla/5.0"}, timeout=5).json()
                us_hosts = []
                for loc in resp.get("data", []):
                    if loc.get("country_code") == "US":
                        for group in loc.get("groups", []):
                            for host in group.get("hosts", []):
                                if host.get("health", 0) >= 3:
                                    us_hosts.append(host["hostname"])

                candidates = [host for host in us_hosts if host != previous_server] or us_hosts
                if candidates:
                    server = random.choice(candidates)
            except Exception as e:
                logger.warning(f"Failed to fetch Windscribe server list (using fallback): {e}")

            _cached_proxy_host = server
            _cached_proxy_time = now
            logger.info(f"Selected Windscribe proxy host: {server} (forced={force_refresh})")
    
    # Windscribe HTTPS proxy on 443 REQUIRES https:// scheme for proper TLS handshake/SNI
    return f"https://{urllib.parse.quote(user)}:{urllib.parse.quote(pw)}@{server}:443"

def stream_video(url):
    is_dailymotion = "dailymotion.com" in url or "dai.ly" in url
    is_youtube = "youtube" in url or "youtu.be" in url
    is_vimeo = "vimeo.com" in url

    max_retries = YOUTUBE_MAX_RETRIES if is_youtube else 2
    slot_acquired = False

    if is_youtube:
        if _recently_failed(url):
            logger.warning(f"Refusing {url}: failed recently (cached for {FAIL_CACHE_SECONDS}s)")
            return
        wait_started = time.monotonic()
        if not _youtube_download_slots.acquire(timeout=SLOT_WAIT_SECONDS):
            logger.warning(f"No YouTube download slot free after {SLOT_WAIT_SECONDS}s for {url}")
            return
        slot_acquired = True
        waited = time.monotonic() - wait_started
        if waited >= 0.1:
            logger.info(f"Waited {waited:.2f}s for a YouTube download slot")

    try:
        for attempt in range(max_retries):
            proxy = get_proxy(force_refresh=is_youtube and attempt > 0)
            # First YouTube attempt skips yt-dlp's forced pre-roll-ad wait (13-18s). If the video
            # does require the ad, that 403s with no data and the retry uses stock yt-dlp.
            if FAST_FIRST_ATTEMPT and is_youtube and attempt == 0 and os.path.exists(FAST_YTDLP):
                cmd = [sys.executable, FAST_YTDLP, url, "-o", "-", "--no-part"]
            else:
                cmd = [sys.executable, "-m", "yt_dlp", url, "-o", "-", "--no-part"]
            extractor_args = [
                "player_client=mweb" if is_youtube and attempt == 0
                else "player_client=mweb,web_embedded,android"
            ]

            cookie_file = None
            if is_youtube:
                # Public videos normally do not need the shared cookie session. Save it
                # as a final fallback so normal traffic does not exhaust that session.
                if attempt == max_retries - 1:
                    cookie_file = COOKIE_FILE
                cmd.extend(["--impersonate", "chrome-110:windows-10"])
            elif is_vimeo:
                cookie_file = COOKIE_FILE_VIMEO
            elif is_dailymotion:
                cookie_file = COOKIE_FILE_DAILYMOTION

            cmd.extend(["--extractor-args", f"youtube:{';'.join(extractor_args)}"])
            cmd.extend(["--extractor-args", f"youtubepot-bgutilhttp:base_url={POT_PROVIDER_URL}"])

            if is_dailymotion:
                cmd.extend(["-f", "best[width<=641]/best[height<=480]/best"])
            elif is_vimeo:
                cmd.extend(["-f", "ba+bv[width<=641]/best[height<=480]/best"])
                proxy = None
            else:
                cmd.extend(["-f", "18/best[ext=mp4][height<=480]/best[width<=641]/best"])

            if cookie_file and os.path.exists(cookie_file):
                cmd.extend(["--cookies", cookie_file])

            env = os.environ.copy()
            env["NO_PROXY"] = "127.0.0.1,localhost,::1,10.126.200.241"
            if proxy:
                env["HTTP_PROXY"] = proxy
                env["HTTPS_PROXY"] = proxy
            else:
                env.pop("HTTP_PROXY", None)
                env.pop("HTTPS_PROXY", None)

            cmd.extend(["--no-check-certificate", "--socket-timeout", "30"])
            if is_youtube:
                # Live broadcasts have no fixed-length format and would otherwise be
                # piped indefinitely, permanently occupying a download slot.
                cmd.extend(["--match-filter", "!is_live & !was_live"])
            logger.info(
                f"Streaming {url} (Attempt {attempt+1}/{max_retries}, "
                f"Proxy: {'Yes' if proxy else 'No'}, Cookies: {'Yes' if cookie_file else 'No'})"
            )

            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                preexec_fn=os.setpgrp, env=env
            )
            ffmpeg_proc = None

            if is_dailymotion:
                ffmpeg_cmd = ["ffmpeg", "-i", "pipe:0", "-bsf:a", "aac_adtstoasc", "-c", "copy", "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-f", "mp4", "pipe:1"]
                ffmpeg_proc = subprocess.Popen(
                    ffmpeg_cmd, stdin=proc.stdout, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, preexec_fn=os.setpgrp
                )
                source_stdout = ffmpeg_proc.stdout
            else:
                source_stdout = proc.stdout

            def log_stderr(p, name):
                if p and p.stderr:
                    for line in iter(p.stderr.readline, b''):
                        text = line.decode(errors="replace").strip()
                        if text:
                            logger.info(f"[{name}] {text}")

            stderr_thread = threading.Thread(
                target=log_stderr, args=(proc, "yt-dlp"), daemon=True
            )
            stderr_thread.start()
            if ffmpeg_proc:
                threading.Thread(
                    target=log_stderr, args=(ffmpeg_proc, "ffmpeg"), daemon=True
                ).start()

            def _kill_children(reason):
                for child in [ffmpeg_proc, proc]:
                    _terminate_group(child)
                logger.warning(f"Killed stream for {url} ({reason})")

            # Hard cap so a stuck/never-ending source (e.g. a live stream that
            # slips past the filter, or a stalled remote) can never hold a
            # download slot forever and starve other requests.
            watchdog = threading.Timer(FIRST_BYTE_SECONDS, _kill_children, args=("no data before first-byte timeout",))
            watchdog.daemon = True
            watchdog.start()
            try:
                first_chunk = source_stdout.read(65536)
                watchdog.cancel()
                if first_chunk:
                    watchdog = threading.Timer(MAX_STREAM_SECONDS, _kill_children, args=("max stream duration exceeded",))
                    watchdog.daemon = True
                    watchdog.start()
                    yield first_chunk
                    while True:
                        chunk = source_stdout.read(65536)
                        if not chunk:
                            break
                        yield chunk
                    return
            finally:
                watchdog.cancel()
                for child in [ffmpeg_proc, proc]:
                    _terminate_group(child)

            stderr_thread.join(timeout=1)
            logger.warning(f"Attempt {attempt+1} produced no data for {url}")
            if attempt + 1 < max_retries:
                time.sleep(0.3 + random.random() * 0.5)

        logger.warning(f"All {max_retries} attempts failed for {url}")
        if is_youtube:
            with _failed_lock:
                _failed_urls[url] = time.time() + FAIL_CACHE_SECONDS
    finally:
        if slot_acquired:
            _youtube_download_slots.release()

def _terminate_group(child):
    """SIGTERM a child's process group, escalate to SIGKILL, then reap it.

    A disconnected Wii must not leave yt-dlp or its ffmpeg child downloading. The leader
    stays unreaped until escalation so its group ID cannot be reused by another process.
    """
    if child is None:
        return
    if child.poll() is not None:
        return
    try:
        pgid = os.getpgid(child.pid)
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return

    def escalate():
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
    threading.Thread(target=escalate, daemon=True).start()

app = Flask(__name__)

ONLINEMEDIA_XML = """<?xml version="1.0" ?>
<file app="WiiMC" version="1.1.1">
  <folder name="YouTube">
    <link name="YouTube - Search" type="search" addr="http://riitube.rc24.xyz/wiimc/?q="/>
    <link name="YouTube - Most Popular" addr="http://riitube.rc24.xyz/wiimc/"/>
    <link name="YouTube - Trending" addr="http://riitube.rc24.xyz/wiimc/?trending=1"/>
  </folder>
  <folder name="Dailymotion">
    <link name="Dailymotion - Search" type="search" addr="http://riitube.rc24.xyz/wiimc/dailymotion/?q="/>
  </folder>
  <folder name="Vimeo">
    <link name="Vimeo - Search" type="search" addr="http://riitube.rc24.xyz/wiimc/vimeo/?q="/>
  </folder>
  <folder name="Radio">
    <folder name="181.fm">
      <folder name="90's Alternative">
        <link name="PLS for WinAMP" addr="http://www.181.fm/stream/pls/181-90salt.pls"/>
        <link name="ASX for wmplayer" addr="http://www.181.fm/stream/asx/181-90salt.asx"/>
      </folder>
      <folder name="90's Country">
        <link name="PLS for WinAMP" addr="http://www.181.fm/stream/pls/181-90scountry.pls"/>
        <link name="ASX for wmplayer" addr="http://www.181.fm/stream/asx/181-90scountry.asx"/>
      </folder>
      <folder name="90's Dance">
        <link name="PLS for WinAMP" addr="http://www.181.fm/stream/pls/181-90sdance.pls"/>
        <link name="ASX for wmplayer" addr="http://www.181.fm/stream/asx/181-90sdance.asx"/>
      </folder>
      <folder name="Awesome 80's">
        <link name="PLS for WinAMP" addr="http://www.181.fm/stream/pls/181-awesome80s.pls"/>
        <link name="ASX for wmplayer" addr="http://www.181.fm/stream/asx/181-awesome80s.asx"/>
      </folder>
      <folder name="Chilled Out">
        <link name="PLS for WinAMP" addr="http://www.181.fm/stream/pls/181-chilledout.pls"/>
        <link name="ASX for wmplayer" addr="http://www.181.fm/stream/asx/181-chilledout.asx"/>
      </folder>
      <folder name="Christmas Mix">
        <link name="PLS for WinAMP" addr="http://www.181.fm/stream/pls/181-xmix.pls"/>
        <link name="ASX for wmplayer" addr="http://www.181.fm/stream/asx/181-xmix.asx"/>
      </folder>
      <folder name="Christmas Rock">
        <link name="PLS for WinAMP" addr="http://www.181.fm/stream/pls/181-xrock.pls"/>
        <link name="ASX for wmplayer" addr="http://www.181.fm/stream/asx/181-xrock.asx"/>
      </folder>
      <folder name="Christmas Smooth Jazz">
        <link name="PLS for WinAMP" addr="http://www.181.fm/stream/pls/181-xsmooth.jazz.pls"/>
        <link name="ASX for wmplayer" addr="http://www.181.fm/stream/asx/181-xsmooth.asx"/>
      </folder>
      <folder name="Classical Guitar">
        <link name="PLS for WinAMP" addr="http://www.181.fm/stream/pls/181-classicalguitar.pls"/>
        <link name="ASX for wmplayer" addr="http://www.181.fm/stream/asx/181-classicalguitar.asx"/>
      </folder>
      <link name="Christmas Blender ASX" addr="http://www.181.fm/stream/asx/181-xblender.asx"/>
      <link name="Christmas Classics ASX" addr="http://www.181.fm/stream/asx/181-xtraditional.asx"/>
      <link name="Christmas Country ASX" addr="http://www.181.fm/stream/asx/181-xcountry.asx"/>
      <link name="Christmas Fun ASX" addr="http://www.181.fm/stream/asx/181-xfun.asx"/>
      <link name="Christmas Gospel ASX" addr="http://www.181.fm/stream/asx/181-xgospel.asx"/>
      <link name="Christmas Highway ASX" addr="http://www.181.fm/stream/asx/181-xhighway.asx"/>
      <link name="Christmas Kids ASX" addr="http://www.181.fm/stream/asx/181-xkids.asx"/>
      <link name="Christmas Oldies ASX" addr="http://www.181.fm/stream/asx/181-xoldies.asx"/>
      <link name="Christmas Soundtracks ASX" addr="http://www.181.fm/stream/asx/181-xsoundtrax.asx"/>
      <link name="Christmas Spirit ASX" addr="http://www.181.fm/stream/asx/181-xspirit.asx"/>
      <link name="Christmas Standards ASX" addr="http://www.181.fm/stream/asx/181-xstandards.asx"/>
      <link name="Christmas Swing ASX" addr="http://www.181.fm/stream/asx/181-xswing.asx"/>
      <link name="Classical Jazz ASX" addr="http://www.181.fm/stream/asx/181-classicaljazz.asx"/>
      <link name="Classical Music ASX" addr="http://www.181.fm/stream/asx/181-classical.asx"/>
    </folder>
  </folder>
</file>"""
@app.route("/onlinemedia.xml")
def onlinemedia_xml():
    return Response(ONLINEMEDIA_XML, mimetype="application/xml")

@app.route("/video/wii/")
def video_wii():
    q, site = request.args.get("q", ""), request.args.get("site", "youtube")
    url = f"https://player.vimeo.com/video/{q}" if site == "vimeo" else (f"https://www.dailymotion.com/video/{q}" if site == "dailymotion" else f"https://www.youtube.com/watch?v={q}")
    return Response(stream_with_context(stream_video(url)), mimetype="application/octet-stream")

def _plx_entry(kind, name, url, thumb=None):
    lines = ["", f"type={kind}", "name=" + " ".join(str(name).splitlines()), f"URL={url}"]
    if thumb:
        lines.append(f"thumb={thumb}")
    return lines

@app.route("/wiimc/")
def wiimc_youtube():
    q = request.args.get("q")
    searching = q is not None
    trending = "trending" in request.args
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    results = []
    fetch_failed = False

    def search_url(number):
        return f"{request.host_url}wiimc/?" + urllib.parse.urlencode({"q": q, "page": number})

    if searching and q:
        search_query = f"ytsearch{page * SEARCH_PAGE_SIZE}:{q}"
        items = f"{(page - 1) * SEARCH_PAGE_SIZE + 1}:{page * SEARCH_PAGE_SIZE}"
    elif trending:
        search_query = "https://www.youtube.com/results?search_query=-dummy&sp=CAMSBAgDEAE%253D"
        items = "1:25"
    else:
        search_query = "https://www.youtube.com/results?search_query=-dummy&sp=CAASBAgDEAE%253D"
        items = "1:25"
    searching = searching and bool(q)

    max_retries = 3
    for attempt in range(max_retries):
        proxy = get_proxy()
        try:
            ydl_opts = {
                'quiet': True, 'extract_flat': True, 'playlist_items': items,
                'skip_download': True, 'nocheckcertificate': True, 'socket_timeout': 15,
                'extractor_retries': 1,
            }
            
            no_proxy_list = "127.0.0.1,localhost,::1,10.126.200.241"
            os.environ["NO_PROXY"] = no_proxy_list
            if proxy: ydl_opts['proxy'] = proxy
            else:
                os.environ.pop("HTTP_PROXY", None)
                os.environ.pop("HTTPS_PROXY", None)

            ydl_opts['extractor_args'] = {
                'youtube': {'player_client': ['mweb', 'web_embedded', 'android']},
                'youtubepot-bgutilhttp': {'base_url': [POT_PROVIDER_URL]},
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                res = ydl.extract_info(search_query, download=False)
                
            if res and 'entries' in res:
                for item in res['entries'][:25]:
                    if item: results.append({'videoId': item.get('id'), 'title': item.get('title', 'Unknown Video')})
            break
        except Exception as e:
            logger.warning(f"yt-dlp search error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                if not searching:
                    return Response(f"Search error: {str(e)}", status=500)
                fetch_failed = True
                break
            time.sleep(0.5)

    # Only well-formed video IDs reach playback and thumbnail URLs.
    results = [r for r in results if isinstance(r.get("videoId"), str) and VIDEO_ID_RE.fullmatch(r["videoId"])]

    if not searching:
        playlist = ["#EXTM3U"]
        for entry in results:
            video_id = entry["videoId"]
            playlist.append(f'#EXTINF:-1="http://i.ytimg.com/vi/{video_id}/mqdefault.jpg",{entry.get("title")}')
            playlist.append(f'{request.host_url}video/wii/?q={video_id}')
        return Response("\n".join(playlist) + "\n", mimetype="text/plain", content_type="text/plain;charset=UTF-8")

    # Search results use WiiMC's PLX format so page links open as playlists.
    # YouTube gives no total page count: a nonempty page offers the next one.
    playlist = ["version=1", f"title=YouTube search - page {page}"]
    if page > 1:
        playlist += _plx_entry("playlist", f"Previous page ({page - 1})", search_url(page - 1))
    for entry in results:
        video_id = entry["videoId"]
        playlist += _plx_entry("video", entry.get("title") or "Unknown Video",
                               f"{request.host_url}video/wii/?q={video_id}",
                               f"http://i.ytimg.com/vi/{video_id}/mqdefault.jpg")
    if fetch_failed:
        playlist += _plx_entry("playlist", "Search failed - select to retry", search_url(page))
    elif results:
        playlist += _plx_entry("playlist", f"Next page ({page + 1})", search_url(page + 1))
    elif page > 1:
        playlist += _plx_entry("playlist", "No more results - back to first page", search_url(1))
    playlist += _plx_entry("search", "New search", f"{request.host_url}wiimc/?q=")
    return Response("\n".join(playlist) + "\n", mimetype="text/plain", content_type="text/plain;charset=UTF-8")

def start_pot_provider():
    if os.path.exists("/usr/local/bin/deno"):
        subprocess.Popen(["/usr/local/bin/deno", "run", "-A", "/root/projects/bgutil-ytdlp-pot-provider/server/src/main.ts", "--port", "4416"], cwd="/root/projects/bgutil-ytdlp-pot-provider/server", stdout=subprocess.DEVNULL)

async def refresh_cookies_async():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        proxy_url = get_proxy()
        launch_args = {"headless": True}
        if proxy_url: launch_args["proxy"] = {"server": proxy_url}
        browser = await p.chromium.launch(**launch_args)
        async def refresh(url, f):
            ctx = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            page = await ctx.new_page()
            try:
                logger.info(f"Refreshing cookies for {url}...")
                await page.goto(url, wait_until="networkidle", timeout=90000)
                await asyncio.sleep(10)
                cookies = await ctx.cookies()
                with open(f, "w") as f_obj:
                    f_obj.write("# Netscape HTTP Cookie File\n")
                    for c in cookies:
                        exp = int(c.get("expires", time.time() + 31536000))
                        domain = c.get("domain", "")
                        is_domain = "TRUE" if domain.startswith(".") else "FALSE"
                        path = c.get("path", "")
                        secure = "TRUE" if c.get("secure", False) else "FALSE"
                        name = c.get("name", "")
                        value = c.get("value", "")
                        f_obj.write(f"{domain}\t{is_domain}\t{path}\t{secure}\t{exp}\t{name}\t{value}\n")
                logger.info(f"Successfully refreshed cookies for {url}")
            except Exception as e: logger.warning(f"Cookie refresh failed for {url}: {e}")
            finally: await ctx.close()
        await refresh("https://www.youtube.com", COOKIE_FILE)
        await browser.close()

def cookie_loop():
    time.sleep(10)
    while True:
        try: asyncio.run(refresh_cookies_async())
        except Exception as e: logger.warning(f"Cookie loop error: {e}")
        time.sleep(43200)

if __name__ == "__main__":
    from waitress import serve
    logger.info(f"Starting RiiTube on port {PORT}...")
    start_pot_provider()
    threading.Thread(target=cookie_loop, daemon=True).start()
    serve(app, host="0.0.0.0", port=PORT, threads=32)
