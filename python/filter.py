from __future__ import annotations
from textual import work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll, Horizontal
from textual.widgets import Input, Markdown, Button, TextArea
import pathlib
import sys
import asyncio
import subprocess
import json
import yaml
from pygments import highlight, lexers, formatters
from pygments.lexers import guess_lexer
import pyperclip
import re
from collections import OrderedDict
import itertools
import jsonlines
import io


class FilterApp(App):
    CSS_PATH = f"{pathlib.Path(__file__).parent.resolve()}/filter.tcss"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_successful_output = ""
        self.custom_python = False
        self.custom_python_cmd = ""

    async def on_mount(self) -> None:
        self.update_filter("")

    def compose(self) -> ComposeResult:
        with Horizontal(id="filter-container"):
            yield Input(placeholder="Enter your filter", id="filter-search")
            yield Button("Copy", id="copy-button")

        with VerticalScroll(id="error-container"):
            yield TextArea(id="error")
        with VerticalScroll(id="results-container"):
            yield TextArea(id="results")

    async def on_input_changed(self, message: Input.Changed) -> None:
        """A coroutine to handle a text changed message."""
        self.update_filter(message.value)

    async def on_button_pressed(self, message: Button.Pressed) -> None:
        """Handle button press events."""
        if message.button.id == "copy-button":
            input_widget = self.query_one("#filter-search", Input)
            pyperclip.copy(input_widget.value)
            self.query_one("#copy-button", Button).label = "Copied to clipboard!"

    @work(exclusive=True)
    async def update_filter(self, word: str) -> None:
        global stdin_input
        check_for_custom_python = re.match(r".*\{\{(.*)\}\}.*", word)
        if check_for_custom_python:
            self.custom_python = True
            self.custom_python_cmd = check_for_custom_python.group(1)
        else:
            self.custom_python = False
        if stdin_input == "":
            if word.strip() == "":
                cmd = f"cat {sys.argv[1]}"
            else:
                cmd = f"cat {sys.argv[1]} | {word}"
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


stdin_input = ""


def parse_stdin_input():
    global stdin_input
    for line in sys.stdin:
        stdin_input += line + "\n"


if __name__ == "__main__":
    app = FilterApp()
    app.run()
