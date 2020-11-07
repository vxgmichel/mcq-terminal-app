"""
An MCQ prompt-toolkit application.
"""

import asyncio
import argparse
from pathlib import Path
from functools import partial

from prompt_toolkit.filters import Condition
from prompt_toolkit.validation import Validator
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit import PromptSession, ANSI, HTML
from prompt_toolkit.application import get_app_session
from prompt_toolkit.formatted_text import to_formatted_text

from .mcqcommon import parse_mcq, read_json, write_json, md_render


def mcq_validate(answer_set, text):
    text_set = set(text.strip().upper())
    return len(text_set) == len(text) and text_set <= answer_set


def mcq_validator(answer):
    return Validator.from_callable(
        lambda text: mcq_validate(set(answer), text),
        error_message="Invalid input",
    )


async def run_mcq_prompts(app_session, mcq_filename, result_dict, dump=None):
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
    if dump is not None:
        dump(result_dict)

    # Loop over entries
    for i, (question, (answers, answer_dict)) in enumerate(
        zip(mcq.questions, mcq.answers), 1
    ):

        # Format the question
        def formatted_question():
            term = app_session.output.term
            columns = app_session.output.get_size().columns
            ansi_question = md_render(question + "\n\n" + answers, term, columns)
            html_prompt = (
                f'⦗ {i} ⦘ <style fg="#aaaaaa">{"/".join(answer_dict)}?</style> '
            )
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


async def run_mcq(mcq_filename, result_dir, username):
    path = Path(result_dir) / f"{username}.json"
    await run_mcq_prompts(
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
