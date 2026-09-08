import shlex
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tools_builtin.shell import run_bash


class ShellStreamingTests(unittest.TestCase):
    def test_progress_arrives_before_command_finishes(self):
        progress = []
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            + shlex.quote("import time; print('first', flush=True); time.sleep(0.2); print('last', flush=True)")
        )
        started = time.monotonic()
        result = run_bash(
            command,
            progress_callback=lambda item: progress.append((time.monotonic(), item["text"])),
        )
        finished = time.monotonic()
        self.assertEqual(result["exit_code"], 0)
        self.assertIn("first", "".join(text for _, text in progress))
        self.assertLess(progress[0][0], finished - 0.1)
        self.assertGreater(finished - started, 0.15)

    def test_stop_event_terminates_child_process(self):
        stop_event = threading.Event()
        first_line = threading.Event()
        result = {}
        command = (
            f"{shlex.quote(sys.executable)} -u -c "
            + shlex.quote("import time; print('started', flush=True); time.sleep(30)")
        )

        def run():
            result["value"] = run_bash(
                command,
                timeout=60,
                stop_event=stop_event,
                progress_callback=lambda item: first_line.set(),
            )

        thread = threading.Thread(target=run)
        thread.start()
        self.assertTrue(first_line.wait(timeout=2))
        stop_event.set()
        thread.join(timeout=4)
        self.assertFalse(thread.is_alive())
        self.assertTrue(result["value"]["stopped"])

    def test_progress_redacts_common_secrets(self):
        progress = []
        command = "printf 'api_key=super-secret\\nAuthorization: Bearer abc123\\n'"
        run_bash(command, progress_callback=lambda item: progress.append(item["text"]))
        output = "".join(progress)
        self.assertNotIn("super-secret", output)
        self.assertNotIn("abc123", output)
        self.assertIn("[REDACTED]", output)

    def test_python_command_uses_current_virtual_environment(self):
        result = run_bash("python -c 'import sys; print(sys.executable)'")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(Path(result["stdout"].strip()).parent, Path(sys.executable).parent)

    def test_quiet_command_emits_running_heartbeat(self):
        progress = []
        with patch("tools_builtin.shell._HEARTBEAT_SECONDS", 0.05):
            result = run_bash(
                f"{shlex.quote(sys.executable)} -c 'import time; time.sleep(.18)'",
                progress_callback=lambda item: progress.append(item["text"]),
            )
        self.assertEqual(result["exit_code"], 0)
        self.assertTrue(any("仍在执行" in item for item in progress))


if __name__ == "__main__":
    unittest.main()
