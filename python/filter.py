from textual import work, on, events
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll, Horizontal
from textual.widgets import TextArea
import pathlib
import sys
import asyncio
import subprocess
import re
from threading import Thread
import multiprocessing


class ExtendedTextArea(TextArea):
    """A subclas of TextArea with key hooks for copying to the clipboard"""

    def on_key(self, event: events.Key) -> None:
        """Handle key press events."""
        if event.key == "c":
            selected = TextArea.selected_text.fget(self)
            if len(selected) > 0:
                self.app.copy_to_clipboard(selected)


class FilterApp(App):
    CSS_PATH = f"{pathlib.Path(__file__).parent.resolve()}/filter.tcss"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_successful_output = ""
        self.custom_python = False
        self.custom_python_cmd = ""
        self.last_input = ""

    async def on_mount(self) -> None:
        self.update_filter()

    def compose(self) -> ComposeResult:
        # with VerticalScroll(id="filter-container"):
        yield ExtendedTextArea().code_editor(id="filter-search", language="bash")
        # yield Button("Copy", id="copy-button")
        yield ExtendedTextArea().code_editor(
            id="error", language="bash", read_only=True
        )
        with VerticalScroll(id="results-container"):
            yield ExtendedTextArea().code_editor(
                id="results", language="json", read_only=True
            )

    @on(TextArea.Changed)
    async def changed(self, message: TextArea.Changed) -> None:
        """A coroutine to handle a text changed message."""
        if message.text_area.id == "filter-search":
            self.update_filter()

    @work(exclusive=True)
    async def update_filter(self) -> None:
        global proc_stdout
        global proc_stderr
        global pipe_mode
        word = self.query_one("#filter-search", TextArea).text
        check_for_custom_python = re.match(r".*\{\{(.*)\}\}.*", word)
        if check_for_custom_python:
            self.custom_python = True
            self.custom_python_cmd = check_for_custom_python.group(1)
        else:
            self.custom_python = False
        if not pipe_mode:
            if len(sys.argv) > 1:
                if word.strip() == "":
                    cmd = f"cat {sys.argv[1]}"
                else:
                    cmd = f"cat {sys.argv[1]} | {word}"
            else:
                cmd = word
            try:
                process = await asyncio.create_subprocess_shell(
                    cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    if stdout:
                        output = stdout.decode("utf-8")
                        self.last_successful_output = self.format_output(output, word)
                        self.query_one("#results", TextArea).text = (
                            self.last_successful_output
                        )
                    self.query_one("#error", TextArea).text = ""
                else:
                    stderr_output = stderr.decode("utf-8").strip().split("\n")[-3:]
                    stderr_display = "\n".join(stderr_output)
                    self.query_one("#error", TextArea).text = (
                        f"Error:\n{stderr_display}"
                    )

            except Exception as e:
                self.query_one("#error", TextArea).text = f"Exception: {str(e)}"
        else:
            self.query_one("#error", TextArea).text = "\n".join(
                proc_stderr.split("\n")[:1000]
            )
            if word.strip() == "":
                self.query_one("#results", TextArea).text = "\n".join(
                    proc_stdout.split("\n")[:1000]
                )
            else:
                process = await asyncio.create_subprocess_shell(
                    word,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE,
                )
                process.stdin.write(proc_stdout.encode("utf-8"))
                stdout, stderr = await process.communicate()
                if process.returncode == 0:
                    if stdout:
                        output = stdout.decode("utf-8")
                        self.last_successful_output = self.format_output(output, word)
                        self.query_one("#results", TextArea).text = (
                            self.last_successful_output
                        )
                    self.query_one("#error", TextArea).text = ""
                else:
                    stderr_output = stderr.decode("utf-8").strip().split("\n")[-3:]
                    stderr_display = "\n".join(stderr_output)
                    self.query_one("#error", TextArea).text = (
                        f"Error:\n{stderr_display}"
                    )

    def format_output(self, output: str, word: str) -> str:
        if self.custom_python:
            new_output = ""
            try:
                for line in output.split("\n"):
                    new_output += line + f",{exec(self.custom_python_cmd)}\n"
                output = new_output
            except:
                pass
        return "\n".join(output.split("\n")[:1000])


proc_stdout = ""
proc_stderr = ""
pipe_mode = False


def enqueue_output(pipe, queue):
    for line in iter(pipe.readline, b""):
        if line:
            queue.put_nowait(line)


def update_std(q, q_type):
    global proc_stdout
    global proc_stderr
    global last_stdout
    global last_stderr
    while True:
        try:
            line = q.get()
            if q_type == "err":
                proc_stderr += line + "\n"
            else:
                proc_stdout += line + "\n"
        except:
            pass


if __name__ == "__main__":
    if len(sys.argv) > 2:
        pipe_mode = True
        process = subprocess.Popen(
            " ".join(sys.argv[1:]),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            text=True,
        )
        stdout_queue = multiprocessing.Manager().Queue()
        stderr_queue = multiprocessing.Manager().Queue()
        stdout_thread = Thread(
            target=enqueue_output, args=(process.stdout, stdout_queue)
        )
        stderr_thread = Thread(
            target=enqueue_output, args=(process.stderr, stderr_queue)
        )
        stdout_thread.daemon = True
        stderr_thread.daemon = True
        stdout_thread.start()
        stderr_thread.start()
        stdout_queue_thread = Thread(target=update_std, args=(stdout_queue, "out"))
        stderr_queue_thread = Thread(target=update_std, args=(stderr_queue, "err"))
        stdout_queue_thread.daemon = True
        stderr_queue_thread.daemon = True
        stdout_queue_thread.start()
        stderr_queue_thread.start()
    app = FilterApp()
    app.run()
