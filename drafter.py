"""
TODO: Finish these
- [ ] Optional bootstrap support
- [ ] Swappable backends
- [ ] Client-side server mode
- [ ] Debug information: show state history
- [ ] Debug information: show current state
- [ ] Debug information: show the page as its original structure
- [ ] Other HTML components

Components to develop:
- [x] Image
- [x] Table
- [ ] Link
- [ ] Button
- [ ] Markdown
- [ ] Textbox
- [ ] Dropdown
- [ ] RadioButtons
- [ ] CheckBox
- [ ] Paragraph
- [ ] BulletList (UnorderedList)
- [ ] NumberedList (OrderedList)
- [ ] Unordered
- [ ] LineBreak
- [ ] HorizontalRule
- [ ] PreformattedText
- [ ] Header
- [ ] Textarea
"""

from typing import Any
from urllib.parse import urlencode, urlparse, parse_qs
import traceback
import inspect
import re
from functools import wraps
from dataclasses import dataclass, is_dataclass, replace, asdict, fields
from dataclasses import field as dataclass_field
import logging
from datetime import datetime

logger = logging.getLogger('cookbook')

try:
    from bottle import Bottle, abort, request
    DEFAULT_BACKEND = "bottle"
except ImportError:
    DEFAULT_BACKEND = "none"
    logger.warn("Bottle unavailable; backend will be disabled and run in test-only mode.")


__version__ = '0.0.2'

def merge_url_query_params(url: str, additional_params: dict) -> str:
    """
    https://stackoverflow.com/a/52373377

    :param url:
    :param additional_params:
    :return:
    """
    url_components = urlparse(url)
    original_params = parse_qs(url_components.query)
    merged_params = dict(**original_params)
    merged_params.update(**additional_params)
    updated_query = urlencode(merged_params, doseq=True)
    return url_components._replace(query=updated_query).geturl()


@dataclass
class Page:
    state: Any
    content: list[str]

    def __init__(self, state, content=None):
        if content is None:
            state, content = None, state
        self.state = state
        self.content = content

        if not isinstance(content, list):
            raise ValueError("The content of a page must be a list of strings.")
        else:
            for chunk in content:
                if not isinstance(chunk, (str, PageContent)):
                    raise ValueError("The content of a page must be a list of strings.")

    def render_content(self) -> str:
        chunked = []
        for chunk in self.content:
            if isinstance(chunk, str):
                chunked.append(f"<p>{chunk}</p>")
            else:
                chunked.append(str(chunk))
        content = "\n".join(chunked)
        return f"<div class='container cookbook-container'><form>{content}</form></div>"

    def verify_content(self, server) -> bool:
        for chunk in self.content:
            if isinstance(chunk, Link):
                chunk.verify(server)
        return True


BASELINE_ATTRS = ["id", "class", "style", "title", "lang", "dir", "accesskey", "tabindex",
                  "onclick", "ondblclick", "onmousedown", "onmouseup", "onmouseover", "onmousemove", "onmouseout",
                  "onkeypress", "onkeydown", "onkeyup",
                  "onfocus", "onblur", "onselect", "onchange", "onsubmit", "onreset", "onabort", "onerror", "onload",
                  "onunload", "onresize", "onscroll"]


class PageContent:
    EXTRA_ATTRS = []

    def verify(self, server) -> bool:
        return True

    def parse_extra_settings(self, **kwargs):
        extra_settings = self.extra_settings.copy()
        extra_settings.update(kwargs)
        styles, attrs = [], []
        for key, value in kwargs.items():
            if key not in self.EXTRA_ATTRS and key not in BASELINE_ATTRS:
                styles.append(f"{key}: {value}")
            else:
                attrs.append(f"{key}={str(value)!r}")
        result = " ".join(attrs)
        if styles:
            result += f" style='{'; '.join(styles)}'"
        return result


class LinkContent:

    def _handle_url(self, url, external):
        if callable(url):
            url = url.__name__
        if external is None:
            external = check_invalid_external_url(url) != ""
        url = url if external else friendly_urls(url)
        return url, external

    def verify(self, server) -> bool:
        if self.url not in server._handle_route:
            invalid_external_url_reason = check_invalid_external_url(self.url)
            if invalid_external_url_reason == "is a valid external url":
                return True
            elif invalid_external_url_reason:
                raise ValueError(f"Link `{self.url}` is not a valid external url.\n{invalid_external_url_reason}.")
            raise ValueError(f"Link `{self.text}` points to non-existent page `{self.url}`.")
        return True


URL_REGEX = "^(?:http(s)?:\/\/)?[\w.-]+(?:\.[\w\.-]+)+[\w\-\._~:/?#[\]@!\$&'\(\)\*\+,;=.]+$"


def check_invalid_external_url(url: str) -> str:
    if url.startswith("file://"):
        return "The URL references a local file on your computer, not a file on a server."
    if re.match(URL_REGEX, url) is not None:
        return "is a valid external url"
    return ""


BASIC_STYLE = """
<style>
    div.cookbook-container {
        padding: 1em;
        border: 1px solid lightgrey;
    }
</style>
"""
INCLUDE_STYLES = {
    'bootstrap': {
        'styles': [
            BASIC_STYLE,
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.3/dist/css/bootstrap.min.css" integrity="sha384-rbsA2VBKQhggwzxH7pPCaAqO46MgnOM80zW1RWuH61DGLwZJEdK2Kadq2F9CUG65" crossorigin="anonymous">',
        ],
        'scripts': [
            '<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.2.3/dist/js/bootstrap.bundle.min.js" integrity="sha384-kenU1KFdBIe4zVF0s0G1M5b4hcpxyD9F7jL+jjXkk+Q2h455rYXK/7HAuoJl+0I4" crossorigin="anonymous"></script>',
            '<script src="https://code.jquery.com/jquery-3.7.1.slim.min.js" integrity="sha256-kmHvs0B+OpCW5GVHUNjv9rOmY0IvSIRcf7zGUDTDQM8=" crossorigin="anonymous"></script>',
        ]
    },
    "skeleton": {
        "styles": [
            BASIC_STYLE,
            '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/skeleton/2.0.4/skeleton.min.css" integrity="sha512-EZLkOqwILORob+p0BXZc+Vm3RgJBOe1Iq/0fiI7r/wJgzOFZMlsqTa29UEl6v6U6gsV4uIpsNZoV32YZqrCRCQ==" crossorigin="anonymous" referrerpolicy="no-referrer" />',
        ],
        "scripts": []
    },
    'none': {
        'styles': [BASIC_STYLE],
        'scripts': []
    }
}

TEMPLATE_200 = """
"""
TEMPLATE_404 = """
<h3>{title}</h3>

<p>{message}</p>

<p>Original error message:</p>
<pre>{error}</pre>

<p>Available routes:</p>
{routes}
"""
TEMPLATE_500 = """
<h3>{title}</h3>

<p>{message}</p>

<p>Original error message:</p>
<pre>{error}</pre>

<p>Available routes:</p>
{routes}
"""

@dataclass
class Link(PageContent, LinkContent):
    text: str
    url: str

    def __init__(self, text: str, url: str, external=None, **kwargs):
        self.text = text
        self.url, self.external = self._handle_url(url, external)
        self.extra_settings = kwargs

    def __str__(self) -> str:
        url = merge_url_query_params(self.url, {'-submit-button': self.text})
        return f"<a href='{url}' {self.parse_extra_settings()}>{self.text}</a>"




@dataclass
class Image(PageContent):
    url: str
    width: int
    height: int

    def __init__(self, url: str, width=None, height=None, **kwargs):
        self.url = url
        self.width = width
        self.height = height
        self.extra_settings = kwargs

    def __str__(self) -> str:
        extra_settings = {}
        if self.width is not None:
            extra_settings['width'] = self.width
        if self.height is not None:
            extra_settings['height'] = self.height
        parsed_settings = self.parse_extra_settings(**extra_settings)
        return f"<img src='{self.url}' {parsed_settings}>"


@dataclass
class Textbox(PageContent):
    name: str
    kind: str
    default_value: str

    def __init__(self, name: str, kind: str = "text", default_value: str = None, **kwargs):
        self.name = name
        self.kind = kind
        self.default_value = default_value
        self.extra_settings = kwargs

    def __str__(self) -> str:
        extra_settings = {}
        if self.default_value is not None:
            extra_settings['value'] = self.default_value
        parsed_settings = self.parse_extra_settings(**extra_settings)
        return f"<input type='{self.kind}' name='{self.name}' {parsed_settings}>"


@dataclass
class Dropdown(PageContent):
    name: str
    options: list[str]
    default_value: str

    def __init__(self, name: str, options: list[str], default_value: str = None, **kwargs):
        self.name = name
        self.options = options
        self.default_value = default_value
        self.extra_settings = kwargs

    def __str__(self) -> str:
        extra_settings = {}
        if self.default_value is not None:
            extra_settings['value'] = self.default_value
        parsed_settings = self.parse_extra_settings(**extra_settings)
        options = "\n".join(f"<option value='{option}'>{option}</option>" for option in self.options)
        return f"<select name='{self.name}' {parsed_settings}>{options}</select>"


@dataclass
class LineBreak(PageContent):
    def __str__(self) -> str:
        return "<br />"


@dataclass
class Button(PageContent, LinkContent):
    text: str
    url: str
    external: bool = False

    def __init__(self, text: str, url: str, external= False, **kwargs):
        self.text = text
        self.url, self.external = self._handle_url(url, external)
        self.extra_settings = kwargs

    def __str__(self) -> str:
        #extra_settings = {}
        #if 'onclick' not in self.extra_settings:
        #    extra_settings['onclick'] = f"window.location.href=\"{self.url}\""
        #parsed_settings = self.parse_extra_settings(**extra_settings)
        #return f"<button {parsed_settings}>{self.text}</button>"
        parsed_settings = self.parse_extra_settings(**self.extra_settings)
        return f"<input type='submit' name='-submit-button' value='{self.text}' formaction='{self.url}' {parsed_settings} />"


@dataclass
class SubmitButton(PageContent, LinkContent):
    text: str
    url: str
    external: bool = False

    def __init__(self, text: str, url: str, external=False, **kwargs):
        self.text = text
        self.url, self.external = self._handle_url(url, external)
        self.extra_settings = kwargs

    def __str__(self) -> str:
        parsed_settings = self.parse_extra_settings(**self.extra_settings)
        return f"<input type='submit' name='-submit-button' value='{self.text}' formaction='{self.url}' {parsed_settings} />"


@dataclass
class _HtmlList(PageContent):
    items: list[Any]
    kind: str = ""

    def __init__(self, items: list[Any], **kwargs):
        self.items = items
        self.extra_settings = kwargs

    def __str__(self) -> str:
        parsed_settings = self.parse_extra_settings(**self.extra_settings)
        items = "\n".join(f"<li>{item}</li>" for item in self.items)
        return f"<{self.kind} {parsed_settings}>{items}</{self.kind}>"

class NumberedList(_HtmlList):
    kind = "ol"

class BulletedList(_HtmlList):
    kind = "ul"


@dataclass
class Header(PageContent):
    body: str
    level: int = 1

    def __str__(self):
        return f"<h{self.level}>{self.body}</h{self.level}>"

@dataclass
class Table(PageContent):
    rows: list[list[str]]

    def __init__(self, rows: list[list[str]], header = None, **kwargs):
        self.rows = rows
        self.header = header
        self.extra_settings = kwargs
        self.reformat_as_tabular()

    def reformat_as_single(self):
        result = []
        for field in fields(self.rows):
            value = getattr(self.rows, field.name)
            result.append([f"<code>{field.name}</code>", f"<code>{field.type.__name__}</code>", f"<code>{value!r}</code>"])
        self.rows = result
        if not self.header:
            self.header = ["Field", "Type", "Current Value"]

    def reformat_as_tabular(self):
        print(self.rows, is_dataclass(self.rows))
        if is_dataclass(self.rows):
            self.reformat_as_single()
            return
        result = []
        had_dataclasses = False
        for row in self.rows:
            if is_dataclass(row):
                had_dataclasses = True
                result.append([str(getattr(row, attr)) for attr in row.__dataclass_fields__])
            if isinstance(row, str):
                result.append(row)
            elif isinstance(row, list):
                result.append([str(cell) for cell in row])

        if had_dataclasses and self.header is None:
            self.header = list(row.__dataclass_fields__.keys())
        self.rows = result

    def __str__(self) -> str:
        parsed_settings = self.parse_extra_settings(**self.extra_settings)
        rows = "\n".join(f"<tr>{''.join(f'<td>{cell}</td>' for cell in row)}</tr>"
                         for row in self.rows)
        header = "" if not self.header else f"<thead><tr>{''.join(f'<th>{cell}</th>' for cell in self.header)}</tr></thead>"
        return f"<table {parsed_settings}>{header}{rows}</table>"


class Text(PageContent):
    body: str

    def __init__(self, body: str):
        self.body = body


def friendly_urls(url: str) -> str:
    if url.strip("/") == "index":
        return "/"
    if not url.startswith('/'):
        url = '/' + url
    return url


@dataclass
class ServerConfiguration:
    host: str = "localhost"
    port: int = 8080
    debug: bool = True
    # "none", "flask", etc.
    backend: str = DEFAULT_BACKEND
    reloader: bool = False
    style: str = 'skeleton'


@dataclass
class VisitedPage:
    url: str
    function: callable
    arguments: str
    status: str
    button_pressed: str
    old_state: Any = None
    started: datetime = dataclass_field(default_factory=datetime.utcnow)
    stopped: datetime = None

    def update(self, new_status):
        self.status = new_status

    def finish(self, new_status):
        self.status = new_status
        self.stopped = datetime.utcnow()

class Server:
    _page_history: list[VisitedPage]

    def __init__(self, **kwargs):
        self.routes = {}
        self._handle_route = {}
        self.default_configuration = ServerConfiguration(**kwargs)
        self._state = None
        self._state_history = []
        self._page_history = []
        self.original_routes = []
        self.app = None

    def reset(self):
        self.routes.clear()

    def add_route(self, url, func):
        if url in self.routes:
            raise ValueError(f"URL `{url}` already exists for an existing routed function: `{func.__name__}`")
        self.original_routes.append((url, func))
        url = friendly_urls(url)
        func = self.make_bottle_page(func)
        self.routes[url] = func
        self._handle_route[url] = self._handle_route[func] = func

    def setup(self, initial_state=None):
        self._state = initial_state
        self.app = Bottle()

        # Setup error pages
        def handle_404(error):
            message = "The requested page was not found."
            # TODO: Only show if not the index
            message += "\n<br>You might want to return to the <a href='/'>index</a> page."
            return TEMPLATE_404.format(title="404 Page not found", message=message,
                                       error=error.body,
                                       routes="\n".join(
                                           f"<li><code>{r!r}</code>: <code>{func}</code></li>" for r, func in
                                           self.original_routes))

        self.app.error(404)(handle_404)
        # Setup routes
        if not self.routes:
            raise ValueError("No routes have been defined.\nDid you remember the @route decorator?")
        for url, func in self.routes.items():
            self.app.route(url, 'GET', func)
        if '/' not in self.routes:
            first_route = list(self.routes.values())[0]
            self.app.route('/', 'GET', first_route)

    def run(self, **kwargs):
        configuration = replace(self.default_configuration, **kwargs)
        self.app.run(**asdict(configuration))

    def prepare_args(self, original_function, args, kwargs):
        args = list(args)
        kwargs = dict(**kwargs)
        button_pressed = ""
        if '-submit-button' in request.params:
            button_pressed = request.params.pop('-submit-button')
        # TODO: Handle non-bottle backends
        for key in list(request.params.keys()):
            kwargs[key] = request.params.pop(key)
        expected_parameters = list(inspect.signature(original_function).parameters.keys())
        if (expected_parameters and expected_parameters[0] == "state") or (
                len(expected_parameters) - 1 == len(args) + len(kwargs)):
            args.insert(0, self._state)
        if len(expected_parameters) < len(args) + len(kwargs):
            self.flash_warning(
                f"The {original_function.__name__} function expected {len(expected_parameters)} parameters, but {len(args) + len(kwargs)} were provided.")
            # TODO: Select parameters to keep more intelligently by inspecting names
            args = args[:len(expected_parameters)]
            while len(expected_parameters) < len(args) + len(kwargs) and kwargs:
                kwargs.pop(list(kwargs.keys())[-1])
        representation = [repr(arg) for arg in args] + [f"{key}={value!r}" for key, value in kwargs.items()]
        return args, kwargs, ", ".join(representation), button_pressed

    def make_bottle_page(self, original_function):
        @wraps(original_function)
        def bottle_page(*args, **kwargs):
            # TODO: Handle non-bottle backends
            url = request.url
            try:
                args, kwargs, arguments, button_pressed = self.prepare_args(original_function, args, kwargs)
            except Exception as e:
                return self.make_error_page("Error preparing arguments for page", e, original_function)
            # Actually start building up the page
            visiting_page = VisitedPage(url, original_function, arguments, "Creating Page", button_pressed)
            self._page_history.append(visiting_page)
            try:
                page = original_function(*args, **kwargs)
            except Exception as e:
                return self.make_error_page("Error creating page", e, original_function)
            visiting_page.update("Verifying Page Result")
            verification_status = self.verify_page_result(page, original_function)
            if verification_status:
                return verification_status
            try:
                page.verify_content(self)
            except Exception as e:
                return self.make_error_page("Error verifying content", e, original_function)
            self._state_history.append(page.state)
            self._state = page.state
            visiting_page.update("Rendering Page Content")
            try:
                content = page.render_content()
            except Exception as e:
                return self.make_error_page("Error rendering content", e, original_function)
            visiting_page.finish("Finished Page Load")
            if self.default_configuration.debug:
                content = content + self.debug_information()
            content = self.wrap_page(content)
            return content

        return bottle_page

    def verify_page_result(self, page, original_function):
        message = ""
        if page is None:
            message = (f"The server did not return a Page object from {original_function}.\n"
                       f"Instead, it returned None (which happens by default when you do not return anything else).\n"
                       f"Make sure you have a proper return statement for every branch!")
        elif isinstance(page, str):
            message = (f"The server did not return a Page() object from {original_function}. Instead, it returned a string:\n"
                       f"  {page!r}\n"
                       f"Make sure you are returning a Page object with the new state and a list of strings!")
        elif isinstance(page, list):
            message = (f"The server did not return a Page() object from {original_function}. Instead, it returned a list:\n"
                       f" {page!r}\n"
                       f"Make sure you return a Page object with the new state and the list of strings, not just the list of strings.")
        elif not isinstance(page, Page):
            message = (f"The server did not return a Page() object from {original_function}. Instead, it returned:\n"
                f" {page!r}\n"
                f"Make sure you return a Page object with the new state and the list of strings.")
        else:
            verification_status = self.verify_page_state_history(page, original_function)
            if verification_status:
                return verification_status
            elif isinstance(page.content, str):
                message = (f"The server did not return a valid Page() object from {original_function}.\n"
                           f"Instead of a list of strings or content objects, the content field was a string:\n"
                    f" {page.content!r}\n"
                    f"Make sure you return a Page object with the new state and the list of strings/content objects.")
            elif not isinstance(page.content, list):
                message = (
                    f"The server did not return a valid Page() object from {original_function}.\n"
                    f"Instead of a list of strings or content objects, the content field was:\n"
                    f" {page.content!r}\n"
                    f"Make sure you return a Page object with the new state and the list of strings/content objects.")
            else:
                for item in page.content:
                    if not isinstance(item, (str, PageContent)):
                        message = (
                            f"The server did not return a valid Page() object from {original_function}.\n"
                            f"Instead of a list of strings or content objects, the content field was:\n"
                            f" {page.content!r}\n"
                            f"One of those items is not a string or a content object. Instead, it was:\n"
                            f" {item!r}\n"
                            f"Make sure you return a Page object with the new state and the list of strings/content objects.")

        if message:
            return self.make_error_page("Error after creating page", ValueError(message), original_function)

    def verify_page_state_history(self, page, original_function):
        if not self._state_history:
            return
        message = ""
        last_type = self._state_history[-1].__class__
        if not isinstance(page.state, last_type):
            message = (
                f"The server did not return a valid Page() object from {original_function}. The state object's type changed from its previous type. The new value is:\n"
                f" {page.state!r}\n"
                f"The most recent value was:\n"
                f" {self._state_history[-1]!r}\n"
                f"The expected type was:\n"
                f" {last_type}\n"
                f"Make sure you return the same type each time.")
        # TODO: Typecheck each field
        if message:
            return self.make_error_page("Error after creating page", ValueError(message), original_function)


    def wrap_page(self, content):
        style = self.default_configuration.style
        if style in INCLUDE_STYLES:
            scripts = INCLUDE_STYLES[style]['scripts']
            styles = INCLUDE_STYLES[style]['styles']
            content = "\n".join(styles) + content + "\n".join(scripts)
        return content

    def make_error_page(self, title, error, original_function):
        tb = traceback.format_exc()
        new_message = f"{title}.\nError in {original_function.__name__}:\n{error}\n\n\n{tb}"
        abort(500, new_message)

    def flash_warning(self, message):
        print(message)

    def debug_information(self):
        page = []
        # Routes
        page.append("<details open><summary>Routes</summary><ul>")
        for original_route, function in self.original_routes:
            parameters = ", ".join(inspect.signature(function).parameters.keys())
            page.append(f"<li><code>{original_route}/</code>: <code>{function.__name__}({parameters})</code></li>")
        page.append("</ul></details>")
        # Current State
        page.append("<details open><summary>State</summary>")
        if self._state is not None:
            page.append(str(Table(self._state)))
        else:
            page.append("<code>None</code>")
        page.append("</details>")
        # Page History
        page.append("<details open><summary>Page Load History</summary><ol reversed>")
        for page_history in reversed(self._page_history):
            button_pressed = f"Clicked <code>{page_history.button_pressed}</code> &rarr; " if page_history.button_pressed else ""
            page.append(f"<li>{button_pressed}{page_history.status} <code>{page_history.url}/</code>: "
                        f"<code>{page_history.function.__name__}({page_history.arguments})</code>:"
                        f""
                        f"</li>")
        page.append("</ol></details>")
        return "\n".join(page)


MAIN_SERVER = Server()


def route(url: str = None, server: Server = MAIN_SERVER):
    if callable(url):
        local_url = url.__name__
        server.add_route(local_url, url)
        return url

    def make_route(func):
        local_url = url
        if url is None:
            local_url = func.__name__
        server.add_route(local_url, func)
        return func

    return make_route


def start_server(initial_state=None, server: Server = MAIN_SERVER, **kwargs):
    server.setup(initial_state)
    server.run(**kwargs)


if __name__ == '__main__':
    print("This package is meant to be imported, not run as a script. For now, at least.")