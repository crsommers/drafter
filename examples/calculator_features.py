from bakery import assert_equal
from dataclasses import dataclass
from drafter import route, start_server, Page, TextBox, SubmitButton, LineBreak


@dataclass
class State:
    first_number: int
    second_number: int
    result: str


@route
def index_page(state: State) -> Page:
    return Page(state, [
        "What is the first number?",
        TextBox("first", state.first_number, "number"),
        "What is the second number?",
        TextBox("second", state.second_number, "number"),
        LineBreak(),
        SubmitButton("Add", add_page),
        SubmitButton("Subtract", subtract_page),
        "The result is",
        state.result
    ])


@route
def add_page(state: State, first: str, second: str) -> Page:
    if not first.isdigit() or not second.isdigit():
        return index_page(state)
    state.first_number = int(first)
    state.second_number = int(second)
    state.result = str(int(first) + int(second))
    return index_page(state)

@route
def subtract_page(state: State, first: str, second: str) -> Page:
    if not first.isdigit() or not second.isdigit():
        return index_page(state)
    state.first_number = int(first)
    state.second_number = int(second)
    state.result = str(int(first) - int(second))
    return index_page(state)


assert_equal(index_page(State(0, 0, "")), Page(State(0, 0, ""), [
    "What is the first number?",
    TextBox("first", "", "number"),
    "What is the second number?",
    TextBox("second", "", "number"),
    SubmitButton("Add", "", "add_page"),
    LineBreak(),
    "The result is",
    ""
]))

assert_equal(add_page(State(0, 0, ""), "5", "3"), Page(State(5, 3, "8"), [
    "What is the first number?",
    TextBox("first", "5", "number"),
    "What is the second number?",
    TextBox("second", "3", "number"),
    SubmitButton("Add", "add_page"),
    LineBreak(),
    "The result is",
    "8",
]))

start_server(State(0, 0, ""), reloader=True)