"""
Common helpers for both versions of the MCQ application
"""

import json
import string
import functools
import subprocess
from collections import namedtuple


@functools.lru_cache(maxsize=None)
def md_render(source, term, width, theme="dark"):
    result = subprocess.run(
        f"glow -s {theme} -w {width - 3} -",
        shell=True,
        capture_output=True,
        input=source,
        text=True,
        env={"TERM": term},
    )
    return result.stdout


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
