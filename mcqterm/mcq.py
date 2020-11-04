"""
An MCQ prompt-toolkit application.
"""

import json
import string
import asyncio
import functools
import subprocess
from pathlib import Path
from functools import partial
from collections import namedtuple

from prompt_toolkit.filters import Condition
from prompt_toolkit.validation import Validator
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit import PromptSession, ANSI, HTML
from prompt_toolkit.application import get_app_session
from prompt_toolkit.formatted_text import to_formatted_text


@functools.lru_cache(maxsize=None)
def md_render(source, term, width, light=False):
    theme = "light" if light else "dark"
    result = subprocess.run(
        f"glow -s {theme} -w {width - 3} -",
        shell=True,
        capture_output=True,
        input=source,
        text=True,
        env={"TERM": term},
    )
    return result.stdout


def mcq_validate(answer_set, text):
    text_set = set(text.strip().upper())
    return len(text_set) == len(text) and text_set <= answer_set


def mcq_validator(answer):
    return Validator.from_callable(
        lambda text: mcq_validate(set(answer), text),
        error_message="Invalid input",
    )


def parse_mcq(filename):

    # Read data file
    with open(filename) as f:
        data = f.read()

    # Extract title, description and questions
    header, *questions, footer = map(str.strip, data.split("\n---\n"))
    title, _, *description = header.splitlines()
    title = title.strip().strip("#")
    description = "\n".join(description).strip()
    footer = footer.strip()

    # Loop over questions
    questions_result = []
    answers_result = []
    for i, question in enumerate(questions, 1):

        # Exctract question
        assert question.startswith(f"# {i}.")
        index = question.strip().rfind("\n- A. ")
        question, answers = map(str.strip, (question[:index], question[index:]))
        questions_result.append(question)

        # Exctract answers
        answer_dict = {}
        for letter, answer in zip(string.ascii_uppercase, answers.splitlines()):
            assert answer.startswith(f"- {letter}. "), (question, letter, answer)
            _, answer = answer.split(f"- {letter}. ", maxsplit=2)
            answer_dict[letter] = answer.strip()
        answers_result.append((answers, answer_dict))

    mcq = namedtuple("mcq", "title, description, header, questions, answers, footer")
    return mcq(title, description, header, questions_result, answers_result, footer)


async def _run_mcq(app_session, mcq_filename, result_dict, dump=None):
    swapped = False
    bindings = KeyBindings()
    prompt_sesion = PromptSession(key_bindings=bindings)

    @bindings.add("c-t")
    def _(event):
        nonlocal swapped
        swapped = not swapped

    def bottom_toolbar(text=""):
        left = text
        right = 'Color swap: <style bg="#222222" fg="#ff8888">[control-t]</style>'
        formatted_left = to_formatted_text(HTML(left))
        formatted_right = to_formatted_text(HTML(right))
        length = sum(len(text) for _, text in formatted_left + formatted_right)
        columns = app_session.output.get_size().columns
        spacing = to_formatted_text(" " * (columns - length))
        return formatted_left + spacing + formatted_right

    # Parse question markdown file
    mcq = parse_mcq(mcq_filename)

    def formatted_header():
        term = app_session.output.term
        columns = app_session.output.get_size().columns
        header = ANSI(md_render(mcq.header, term, columns))
        return to_formatted_text(header) + to_formatted_text(">>> ")

    name = await prompt_sesion.prompt_async(
        formatted_header,
        default=result_dict["name"],
        bottom_toolbar=lambda: bottom_toolbar("Please enter your name"),
        swap_light_and_dark_colors=Condition(lambda: swapped),
    )
    result_dict["name"] = name

    # Loop over entries
    for i, (question, (answers, answer_dict)) in enumerate(
        zip(mcq.questions, mcq.answers), 1
    ):

        # Format the question
        def formatted_question():
            term = app_session.output.term
            columns = app_session.output.get_size().columns
            ansi_question = md_render(question + "\n\n" + answers, term, columns)
            html_prompt = f'⦗ {i} ⦘ <style fg="#aaaaaa">{"/".join(answer_dict)}?</style> '
            return to_formatted_text(ANSI(ansi_question)) + to_formatted_text(
                HTML(html_prompt)
            )

        # Prompt for tentative answer
        default = result_dict["answers"].get(f"{i}", "")
        tentative = await prompt_sesion.prompt_async(
            formatted_question,
            default=default,
            validator=mcq_validator(answer_dict),
            validate_while_typing=True,
            bottom_toolbar=lambda: bottom_toolbar("Pick zero, one or more answers"),
            swap_light_and_dark_colors=Condition(lambda: swapped),
        )

        # Normalize tentative answer
        tentative = "".join(sorted(tentative.upper().strip()))
        result_dict["answers"][f"{i}"] = tentative
        if dump is not None:
            dump(result_dict)

    def formatted_footer():
        term = app_session.output.term
        columns = app_session.output.get_size().columns
        footer = ANSI(md_render(mcq.footer, term, columns))
        return to_formatted_text(footer) + to_formatted_text(">>> ")

    message = "Optionally enter a comment and exit"
    comment = await prompt_sesion.prompt_async(
        formatted_footer,
        default=result_dict["comment"],
        bottom_toolbar=lambda: bottom_toolbar(message),
        swap_light_and_dark_colors=Condition(lambda: swapped),
        validator=Validator.from_callable(lambda _: True),
        validate_while_typing=False,
    )
    result_dict["comment"] = comment
    if dump is not None:
        dump(result_dict)

    return result_dict


def read_json(path):
    try:
        value = json.loads(path.read_text())
    except (ValueError, json.JSONDecodeError, OSError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    value.setdefault("name", "")
    value.setdefault("answers", {})
    value.setdefault("comment", "")
    return value


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


async def run_mcq(mcq_filename, result_dir, username):
    path = Path(result_dir) / f"{username}.json"
    await _run_mcq(
        get_app_session(),
        mcq_filename,
        read_json(path),
        partial(write_json, path)
    )


if __name__ == "__main__":
    asyncio.run(run_mcq("example/mcq-example.md", "results", "reference"))
