"""Windows process cleanup, without Codex credentials or model calls."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import platform
import sys
import tempfile
import threading
import time
import unittest

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from review_worker import _run_process
from validate_review_result import ReviewError


class WindowsProcessTests(unittest.TestCase):
    # @test-value v2
    # kind = "regression"
    # claim = "timeoutとcancelで所有する親子processを終了し、正常なreview結果として返さない"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "primary processだけを止めて子を残すか、期限切れを意味上のverdictとして扱う"
    # observable = "失敗codeと全PIDの終了状態"
    # observation_boundary = "component-behavior"
    # scope = "single-review-process-cleanup"
    # lifecycle = "permanent"
    # @end-test-value
    @unittest.skipUnless(platform.system() == "Windows", "Windows Job Object required")
    def test_timeout_and_cancel_terminate_owned_process_tree(self):
        program = (
            "import os,subprocess,sys,time;from pathlib import Path;"
            "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
            "Path(sys.argv[1]).write_text(str(os.getpid())+' '+str(child.pid));"
            "time.sleep(60)"
        )
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        for cancel_run in (False, True):
            with self.subTest(cancel=cancel_run), tempfile.TemporaryDirectory() as tmp:
                marker = Path(tmp) / "pids.txt"
                cancel = threading.Event()
                timer = threading.Timer(2.5, cancel.set) if cancel_run else None
                if timer:
                    timer.start()
                try:
                    with self.assertRaises(ReviewError) as caught:
                        _run_process([sys.executable, "-c", program, str(marker)], "", Path(tmp),
                                     time.monotonic() + 9, cancel, os.environ.copy())
                finally:
                    if timer:
                        timer.cancel()
                        timer.join()
                self.assertEqual(caught.exception.code, "CANCELLED" if cancel_run else "REVIEW_TIMEOUT")
                self.assertTrue(marker.is_file(), "both processes must have started")
                for pid in marker.read_text().split():
                    handle = kernel.OpenProcess(0x00100000, False, int(pid))
                    if handle:
                        try:
                            self.assertEqual(kernel.WaitForSingleObject(handle, 0), 0)
                        finally:
                            kernel.CloseHandle(handle)


if __name__ == "__main__":
    unittest.main()
