"""
An MCQ prompt-toolkit application.
"""

import asyncio
import argparse
from pathlib import Path
from functools import partial
from importlib import resources

from prompt_toolkit import ANSI
from prompt_toolkit.styles import Style
from prompt_toolkit.layout import Layout
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit
from prompt_toolkit.application import get_app_session
from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.key_binding.defaults import load_key_bindings, merge_key_bindings
from prompt_toolkit.widgets import (
    Button,
    CheckboxList,
    Dialog,
    Label,
    TextArea,
)

from .mcqcommon import parse_mcq, md_render, read_json, write_json

NAME_PROMPT = "Please enter your name"
BEGIN_TEXT = "Begin"
NEXT_TEXT = "Next"
PREVIOUS_TEXT = "Previous"
EXIT_TEXT = "Exit"

STYLE = Style.from_dict(
    {
        "dialog": "bg:",
        "dialog frame.label": "bg:#ffffff #110011",
        "dialog.body": "bg:#110011 #22aa22",
        "dialog shadow": "bg:#226622",
        "text-area": "bg:#223311 #dddddd",
        "button.focused": "bg:#226622 #dddddd",
    }
)


class MCQApp:
    def __init__(self, app_session, mcq_data, result_dict, dump):
        # Set arguments
        self.app_session = app_session
        self.mcq_data = mcq_data
        self.result_dict = result_dict
        self.dump = dump

        # Set MCQ data
        self.title = mcq_data.title
        self.description = mcq_data.description
        self.footer = mcq_data.footer
        self.questions = dict(enumerate(mcq_data.questions, 1))
        self.answers = dict(
            enumerate((answer_dict for _, answer_dict in mcq_data.answers), 1)
        )

        # Set current question
        self.current = 0
        self.bindings = self._make_bindings()
        self.app = self._make_app(Label(""), self.bindings)

        # Inputs
        self.name_input = TextArea(
            result_dict["name"], multiline=False, accept_handler=self.next_handler
        )
        self.comment_input = TextArea(result_dict["comment"], multiline=True)

        # Update dialog
        self.update_dialog()

    def update_dialog(self):
        self.name_input.text = self.result_dict["name"]
        self.comment_input.text = self.result_dict["comment"]
        self.cb_list = self._make_cb_list(self.current)
        self.body = self._make_body(self.current, self.cb_list)
        self.dialog = self._make_dialog(self.current, self.title, self.body)
        self.app.layout = Layout(self.dialog)
        self.app.invalidate()
        self.app.layout.focus(self.dialog)

    # Helpers

    def render(self, source):
        term = self.app_session.output.term
        width = self.app_session.output.get_size().columns - 4
        with resources.path('mcqterm', 'custom-glow-theme.json') as theme:
            return to_formatted_text(
                ANSI(md_render(source, term, width, theme).strip())
            )

    def save(self):
        if self.cb_list is None:
            self.result_dict["name"] = self.name_input.buffer.text
            self.result_dict["comment"] = self.comment_input.buffer.text
        else:
            current_answer = "".join(sorted(self.cb_list.current_values))
            self.result_dict["answers"][f"{self.current}"] = current_answer
        if self.dump is not None:
            self.dump(self.result_dict)

    # Make methods

    def _make_cb_list(self, current):
        if current == 0 or current == len(self.answers) + 1:
            return None
        answers = self.answers[current]
        values = [(key, self.render(value)) for key, value in answers.items()]
        cb_list = CheckboxList(values)
        cb_list.show_scrollbar = False
        cb_list.current_values = list(self.result_dict["answers"].get(f"{current}", ""))
        original_method = cb_list._handle_enter

        def _handle_enter():
            original_method()
            self.save()

        cb_list._handle_enter = _handle_enter
        return cb_list

    def _make_body(self, current, cb_list):
        if current == 0:
            return self._make_first_body()
        if current == len(self.answers) + 1:
            return self._make_last_body()
        question = self.questions[current]
        assert cb_list is not None
        return [Label(text=self.render(question), dont_extend_height=True), cb_list]

    def _make_first_body(self):
        label = Label(text=self.render(self.description), dont_extend_height=True)
        label2 = Label(text=f"\n{NAME_PROMPT}:", dont_extend_height=True)
        return [label, label2, self.name_input]

    def _make_last_body(self):
        label = Label(text=self.render(self.footer), dont_extend_height=True)
        return [label, self.comment_input]

    def _make_dialog(self, current, title, body):
        if current == 0:
            buttons = [
                Button(text=BEGIN_TEXT, handler=self.next_handler),
            ]
        elif current == len(self.answers) + 1:
            buttons = [
                Button(text=PREVIOUS_TEXT, handler=self.previous_handler),
                Button(text=EXIT_TEXT, handler=self.exit_handler),
            ]
        else:
            buttons = [
                Button(text=PREVIOUS_TEXT, handler=self.previous_handler),
                Button(text=NEXT_TEXT, handler=self.next_handler),
            ]
        return Dialog(
            title=title,
            body=HSplit(body, padding=1),
            buttons=buttons,
            with_background=True,
        )

    def _make_bindings(self):
        bindings = KeyBindings()
        bindings.add("tab")(focus_next)
        bindings.add("s-tab")(focus_previous)
        bindings.add("right")(focus_next)
        bindings.add("left")(focus_previous)
        bindings.add("c-c")(self.exit_handler)
        bindings.add("c-d")(self.exit_handler)
        return bindings

    def _make_app(self, dialog, bindings):
        return Application(
            layout=Layout(dialog),
            key_bindings=merge_key_bindings([load_key_bindings(), bindings]),
            mouse_support=True,
            full_screen=True,
            style=STYLE,
        )

    # Handler methods

    def exit_handler(self, arg=None):
        self.save()
        self.app.exit()

    def previous_handler(self, arg=None):
        self.save()
        self.current -= 1
        self.update_dialog()

    def next_handler(self, arg=None):
        self.save()
        self.current += 1
        self.update_dialog()


async def _run_mcq(app_session, mcq_filename, result_dict, dump=None):
    mcq_data = parse_mcq(mcq_filename)
    mcq_app = MCQApp(app_session, mcq_data, result_dict, dump)
    await mcq_app.app.run_async()


async def run_mcq(mcq_filename, result_dir, username):
    path = Path(result_dir) / f"{username}.json"
    await _run_mcq(
        get_app_session(), mcq_filename, read_json(path), partial(write_json, path)
    )


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", "-u", type=str, default="reference")
    parser.add_argument("--result-dir", "-r", type=Path, default=Path("results"))
    parser.add_argument("mcq_filename", metavar="MCQ_FILE", type=Path)
    namespace = parser.parse_args(args)
    asyncio.run(run_mcq(namespace.mcq_filename, namespace.result_dir, namespace.username))


if __name__ == "__main__":
    main()
