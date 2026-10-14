import io
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

import requests


SCRIPT = Path(__file__).resolve().parents[1] / "wiimc" / "index.cgi"
VIDEO = {"videoId": "jNQXAC9IVRw", "title": "Me at the zoo"}


class SearchTests(unittest.TestCase):
    def run_search(self, query_string, entries=None, error=None):
        output = io.StringIO()
        errors = io.StringIO()
        response = Mock()
        response.json.return_value = [VIDEO] if entries is None else entries
        environment = {"REQUEST_METHOD": "GET", "QUERY_STRING": query_string}
        with patch.dict(os.environ, environment, clear=True), \
                patch("sys.stdout", output), patch("sys.stderr", errors), \
                patch.object(requests, "get", return_value=response, side_effect=error) as get:
            runpy.run_path(str(SCRIPT), run_name="__main__")
        return output.getvalue(), errors.getvalue(), get

    def playlist_entries(self, output):
        entries = []
        for line in output.splitlines():
            if line.startswith("type="):
                entries.append({})
            if entries and "=" in line:
                key, value = line.split("=", 1)
                entries[-1][key] = value
        return entries

    def test_first_page_has_typed_navigation_and_video_thumbnail(self):
        output, _, get = self.run_search("q=cats")
        entries = self.playlist_entries(output)
        self.assertIn("version=1", output)
        self.assertEqual([entry["type"] for entry in entries], ["video", "playlist", "search"])
        self.assertEqual(entries[0]["URL"], "http://riitube.rc24.xyz/video/wii/?q=jNQXAC9IVRw")
        self.assertEqual(entries[0]["thumb"], "http://i.ytimg.com/vi/jNQXAC9IVRw/mqdefault.jpg")
        self.assertEqual(entries[1]["name"], "Next page (2)")
        self.assertEqual(parse_qs(urlsplit(get.call_args.args[0]).query),
                         {"q": ["cats"], "page": ["1"], "type": ["video"]})

    def test_page_links_round_trip_reserved_characters_and_unicode(self):
        query = "cats & dogs + # café /?"
        output, _, _ = self.run_search(urlencode({"q": query}))
        next_page = self.playlist_entries(output)[1]
        self.assertEqual(parse_qs(urlsplit(next_page["URL"]).query), {"q": [query], "page": ["2"]})
        output, _, get = self.run_search(urlsplit(next_page["URL"]).query)
        entries = self.playlist_entries(output)
        self.assertEqual(entries[0]["name"], "Previous page (1)")
        self.assertEqual(parse_qs(urlsplit(entries[0]["URL"]).query), {"q": [query], "page": ["1"]})
        self.assertEqual(parse_qs(urlsplit(get.call_args.args[0]).query)["page"], ["2"])

    def test_invalid_pages_start_at_the_first_page(self):
        for page in ("0", "-1", "oops", "1.5", ""):
            with self.subTest(page=page):
                output, _, get = self.run_search(urlencode({"q": "cats", "page": page}))
                self.assertNotIn("Previous page", output)
                self.assertEqual(parse_qs(urlsplit(get.call_args.args[0]).query)["page"], ["1"])

    def test_empty_later_page_retains_a_way_back_without_next_page(self):
        output, _, _ = self.run_search("q=cats&page=3", entries=[])
        entries = self.playlist_entries(output)
        self.assertEqual(entries[0]["name"], "Previous page (2)")
        self.assertNotIn("Next page", output)
        self.assertIn("No more results", output)
        self.assertEqual(entries[-1]["type"], "search")

    def test_empty_first_page_still_allows_another_search(self):
        output, _, _ = self.run_search("q=cats", entries=[])
        self.assertEqual(self.playlist_entries(output), [{
            "type": "search", "name": "New search", "URL": "http://riitube.rc24.xyz/wiimc/?q="
        }])

    def test_timeout_keeps_the_page_and_offers_a_retry(self):
        output, errors, _ = self.run_search("q=cats&page=3", error=requests.Timeout("timeout"))
        entries = self.playlist_entries(output)
        self.assertEqual(entries[0]["name"], "Previous page (2)")
        self.assertIn("retry", entries[1]["name"])
        self.assertEqual(parse_qs(urlsplit(entries[1]["URL"]).query), {"q": ["cats"], "page": ["3"]})
        self.assertNotIn("Next page", output)
        self.assertIn("timeout", errors)

    def test_invalid_api_response_is_retryable(self):
        output, errors, _ = self.run_search("q=cats", entries={"error": "unavailable"})
        self.assertIn("select to retry", output)
        self.assertNotIn("Next page", output)
        self.assertIn("unavailable", errors)

    def test_unsupported_entries_and_multiline_titles_do_not_break_plx(self):
        entries = [None, {"type": "channel"}, {
            "videoId": VIDEO["videoId"], "title": "hello\ntype=playlist\nURL=http://evil.test"
        }]
        output, _, _ = self.run_search("q=cats", entries=entries)
        self.assertEqual(output.count("\ntype="), 3)
        self.assertNotIn("\nURL=http://evil.test", output)
        self.assertEqual(self.playlist_entries(output)[0]["type"], "video")

    def test_trending_and_popular_keep_their_m3u_output(self):
        for query, endpoint in (("trending=1", "trending"), ("", "popular")):
            with self.subTest(endpoint=endpoint):
                output, _, get = self.run_search(query)
                self.assertIn("#EXTM3U\n", output)
                self.assertIn('#EXTINF:-1="http://i.ytimg.com/vi/jNQXAC9IVRw/mqdefault.jpg",Me at the zoo', output)
                self.assertNotIn("version=1", output)
                self.assertEqual(get.call_args.args[0], "http://95.217.72.119:29864/api/v1/" + endpoint)


if __name__ == "__main__":
    unittest.main()
