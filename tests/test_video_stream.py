import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "video" / "wii" / "index.cgi"
BODY = bytes(range(256)) * 512
DIAGNOSTICS = b"progress\n" * 131072
CHILD = r'''
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(os.environ["STREAM_TEST_DIR"])
mode = os.environ["STREAM_TEST_MODE"]
fallback = sys.argv[1] == "fallback"
(root / ("fallback.pid" if fallback else "primary.pid")).write_text(str(os.getpid()))
if fallback:
    sys.stderr.buffer.write(b"progress\n" * 131072)
    sys.stderr.flush()
    sys.stdout.buffer.write(b"fallback")
    sys.stdout.flush()
elif mode == "empty":
    sys.stderr.write("download failed\n")
    sys.exit(2)
elif mode == "small":
    sys.stdout.buffer.write(b"first")
    sys.stdout.flush()
    time.sleep(60)
elif mode == "silent":
    time.sleep(60)
elif mode in ("disconnect", "stubborn"):
    code = "import time; time.sleep(60)"
    if mode == "stubborn":
        code = (
            "import os, signal, time; from pathlib import Path; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "Path(os.environ['STREAM_TEST_DIR'], 'grandchild.ready').touch(); "
            "time.sleep(60)"
        )
    child = subprocess.Popen([sys.executable, "-c", code])
    (root / "grandchild.pid").write_text(str(child.pid))
    if mode == "stubborn":
        while not (root / "grandchild.ready").exists():
            time.sleep(0.01)
    while True:
        sys.stdout.buffer.write(b"data" * 2048)
        sys.stdout.flush()
else:
    if mode == "signed":
        sys.stderr.write("Input: https://example.test/video.mp4?token=private-token\n")
    sys.stderr.buffer.write(b"progress\n" * 131072)
    sys.stderr.flush()
    sys.stdout.buffer.write(bytes(range(256)) * 512)
    sys.stdout.flush()
    if mode == "partial":
        sys.exit(2)
'''
HARNESS = r'''
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

root = Path(os.environ["STREAM_TEST_DIR"])
real_popen = subprocess.Popen
def popen(command, **options):
    with (root / "commands.jsonl").open("a") as log:
        log.write(json.dumps(command) + "\n")
    fallback = any("transfer.archivete.am" in argument for argument in command)
    return real_popen([sys.executable, str(root / "child.py"),
                       "fallback" if fallback else "primary"], **options)
subprocess.Popen = popen
subprocess.check_output = lambda *args, **kwargs: "https://example.test/video.mp4"
runpy.run_path(sys.argv[1], run_name="__main__")
'''


class VideoStreamTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "child.py").write_text(CHILD)
        self.processes = []

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            process.wait()
            for stream in (process.stdout, process.stderr):
                if stream and not stream.closed:
                    stream.close()
        for file in self.root.glob("*.pid"):
            pid = int(file.read_text())
            if self.alive(pid):
                os.kill(pid, signal.SIGKILL)
        self.temp.cleanup()

    def alive(self, pid):
        try:
            return Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"
        except FileNotFoundError:
            return False

    def start_cgi(self, mode="loud", query="q=jNQXAC9IVRw"):
        environment = dict(os.environ, REQUEST_METHOD="GET", QUERY_STRING=query,
                           STREAM_TEST_DIR=str(self.root), STREAM_TEST_MODE=mode)
        process = subprocess.Popen([sys.executable, "-c", HARNESS, str(SCRIPT)],
                                   env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.processes.append(process)
        return process

    def read_until(self, process, marker):
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            output = b""
            deadline = time.monotonic() + 5
            while marker not in output and time.monotonic() < deadline:
                if selector.select(timeout=0.1):
                    chunk = os.read(process.stdout.fileno(), 8192)
                    if not chunk:
                        break
                    output += chunk
        self.assertIn(marker, output)
        return output

    def test_large_diagnostics_cannot_block_the_video_pipe(self):
        for query in ("q=jNQXAC9IVRw", "site=vimeo&q=123", "site=dailymotion&q=x123"):
            with self.subTest(query=query):
                process = self.start_cgi(query=query)
                output, errors = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0)
                self.assertEqual(output.split(b"\n\n", 1)[1], BODY)
                if query.startswith("site=dailymotion"):
                    self.assertNotIn(DIAGNOSTICS, errors)
                else:
                    self.assertIn(DIAGNOSTICS, errors)
                self.assertFalse(self.alive(int((self.root / "primary.pid").read_text())))

    def test_empty_primary_uses_fallback_without_blocking_on_its_diagnostics(self):
        process = self.start_cgi(mode="empty")
        output, errors = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(output.split(b"\n\n", 1)[1], b"fallback")
        self.assertIn(DIAGNOSTICS, errors)
        self.assertIn(b"status 2", errors)

    def test_partial_failure_does_not_append_fallback_to_a_video(self):
        process = self.start_cgi(mode="partial")
        output, errors = process.communicate(timeout=10)
        self.assertEqual(output.split(b"\n\n", 1)[1], BODY)
        self.assertIn(b"status 2", errors)
        self.assertFalse((self.root / "fallback.pid").exists())

    def test_small_first_chunk_is_forwarded_before_the_downloader_finishes(self):
        process = self.start_cgi(mode="small")
        self.read_until(process, b"first")
        self.assertIsNone(process.poll())
        process.stdout.close()
        process.wait(timeout=10)

    def test_disconnect_stops_downloader_and_its_child_without_fallback(self):
        process = self.start_cgi(mode="disconnect")
        self.read_until(process, b"data")
        process.stdout.close()
        process.wait(timeout=10)
        self.assertEqual(process.returncode, 0)
        for name in ("primary.pid", "grandchild.pid"):
            self.assertFalse(self.alive(int((self.root / name).read_text())), name)
        self.assertFalse((self.root / "fallback.pid").exists())

    def test_disconnect_kills_a_stubborn_child_after_the_leader_exits(self):
        process = self.start_cgi(mode="stubborn")
        self.read_until(process, b"data")
        process.stdout.close()
        process.wait(timeout=10)
        self.assertEqual(process.returncode, 0)
        for name in ("primary.pid", "grandchild.pid"):
            self.assertFalse(self.alive(int((self.root / name).read_text())), name)
        self.assertFalse((self.root / "fallback.pid").exists())

    def test_disconnect_while_downloader_is_silent_stops_it_without_fallback(self):
        process = self.start_cgi(mode="silent")
        self.read_until(process, b"\n\n")
        deadline = time.monotonic() + 5
        while not (self.root / "primary.pid").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue((self.root / "primary.pid").exists())
        process.stdout.close()
        process.wait(timeout=10)
        self.assertEqual(process.returncode, 0)
        self.assertFalse(self.alive(int((self.root / "primary.pid").read_text())))
        self.assertFalse((self.root / "fallback.pid").exists())

    def test_dailymotion_signed_input_url_is_not_logged(self):
        process = self.start_cgi(mode="signed", query="site=dailymotion&q=x123")
        output, errors = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(output.split(b"\n\n", 1)[1], BODY)
        self.assertFalse(b"private-token" in errors, "signed input token was logged")
        self.assertFalse(b"https://example.test/video.mp4" in errors, "signed input URL was logged")


if __name__ == "__main__":
    unittest.main()
