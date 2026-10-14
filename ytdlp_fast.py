# yt-dlp launcher: skip the forced pre-roll-ad wait (available_at) so streams start immediately.
import sys
from yt_dlp.extractor.youtube._video import YoutubeIE
YoutubeIE._get_available_at_timestamp = lambda self, *a, **k: int(__import__("time").time())
import yt_dlp
if __name__ == "__main__":
    yt_dlp.main()
