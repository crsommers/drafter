from dataclasses import dataclass, is_dataclass, fields
from typing import Any, Union
import io
import base64
# from urllib.parse import quote_plus
import json
import html

from drafter.constants import LABEL_SEPARATOR, SUBMIT_BUTTON_KEY, JSON_DECODE_SYMBOL
from drafter.urls import remap_attr_styles, friendly_urls, check_invalid_external_url, merge_url_query_params
from drafter.image_support import HAS_PILLOW

try:
    import matplotlib.pyplot as plt
    _has_matplotlib = True
except ImportError:
    _has_matplotlib = False


BASELINE_ATTRS = ["id", "class", "style", "title", "lang", "dir", "accesskey", "tabindex", "value",
                  "onclick", "ondblclick", "onmousedown", "onmouseup", "onmouseover", "onmousemove", "onmouseout",
                  "onkeypress", "onkeydown", "onkeyup",
                  "onfocus", "onblur", "onselect", "onchange", "onsubmit", "onreset", "onabort", "onerror", "onload",
                  "onunload", "onresize", "onscroll"]


class PageContent:
    """
    Base class for all content that can be added to a page.
    This class is not meant to be used directly, but rather to be subclassed by other classes.
    Critically, each subclass must implement a ``__str__`` method that returns the HTML representation.

    Under most circumstances, a string value can be used in place of a ``PageContent`` object
    (in which case we say it is a ``Content`` type). However, the ``PageContent`` object
    allows for more customization and control over the content.

    Ultimately, the ``PageContent`` object is converted to a string when it is rendered.

    This class also has some helpful methods for verifying URLs and handling attributes/styles.
    """
    EXTRA_ATTRS = []
    extra_settings: dict

    def verify(self, server) -> bool:
        return True

    def parse_extra_settings(self, **kwargs):
        extra_settings = self.extra_settings.copy()
        extra_settings.update(kwargs)
        raw_styles, raw_attrs = remap_attr_styles(extra_settings)
        styles, attrs = [], []
        for key, value in raw_attrs.items():
            if key not in self.EXTRA_ATTRS and key not in BASELINE_ATTRS:
                styles.append(f"{key}: {value}")
            else:
                attrs.append(f"{key}={str(value)!r}")
        for key, value in raw_styles.items():
            styles.append(f"{key}: {value}")
        result = " ".join(attrs)
        if styles:
            result += f" style='{'; '.join(styles)}'"
        return result

    def update_style(self, style, value):
        self.extra_settings[f"style_{style}"] = value
        return self

    def update_attr(self, attr, value):
        self.extra_settings[attr] = value
        return self

    def render(self, current_state, configuration):
        return str(self)


Content = Union[PageContent, str]


class LinkContent:
    def _handle_url(self, url, external=None):
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

    def create_arguments(self, arguments, label_namespace):
        parameters = self.parse_arguments(arguments, label_namespace)
        if parameters:
            return "\n".join(f"<input type='hidden' name='{name}' value='{html.escape(json.dumps(value), True)}' />"
                             for name, value in parameters.items())
        return ""

    def parse_arguments(self, arguments, label_namespace):
        if arguments is None:
            return {}
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, Argument):
            return {f"{label_namespace}{LABEL_SEPARATOR}{arguments.name}": arguments.value}
        if isinstance(arguments, list):
            result = {}
            for arg in arguments:
                if isinstance(arg, Argument):
                    arg, value = arg.name, arg.value
                else:
                    arg, value = arg
                result[f"{label_namespace}{LABEL_SEPARATOR}{arg}"] = value
            return result
        raise ValueError(f"Could not create arguments from the provided value: {arguments}")


@dataclass
class Argument(PageContent):
    name: str
    value: Any

    def __init__(self, name: str, value: Any, **kwargs):
        self.name = name
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"Argument values must be strings, integers, floats, or booleans. Found {type(value)}")
        self.value = value
        self.extra_settings = kwargs

    def __str__(self) -> str:
        value = html.escape(json.dumps(self.value), True)
        return f"<input type='hidden' name='{JSON_DECODE_SYMBOL}{self.name}' value='{value}' {self.parse_extra_settings()} />"


@dataclass
class Link(PageContent, LinkContent):
    text: str
    url: str

    def __init__(self, text: str, url: str, arguments=None, **kwargs):
        self.text = text
        self.url, self.external = self._handle_url(url)
        self.extra_settings = kwargs
        self.arguments = arguments

    def __str__(self) -> str:
        precode = self.create_arguments(self.arguments, self.text)
        url = merge_url_query_params(self.url, {SUBMIT_BUTTON_KEY: self.text})
        return f"{precode}<a href='{url}' {self.parse_extra_settings()}>{self.text}</a>"


BASE_IMAGE_FOLDER = "/__images"


@dataclass
class Image(PageContent, LinkContent):
    url: str
    width: int
    height: int

    def __init__(self, url: str, width=None, height=None, **kwargs):
        self.url = url
        self.width = width
        self.height = height
        self.extra_settings = kwargs
        self.base_image_folder = BASE_IMAGE_FOLDER

    def render(self, current_state, configuration):
        self.base_image_folder = configuration.deploy_image_path
        return super().render(current_state, configuration)

    def _handle_pil_image(self, image):
        if not HAS_PILLOW or isinstance(image, str):
            return False, image

        image_data = io.BytesIO()
        image.save(image_data, format="PNG")
        image_data.seek(0)
        figure = base64.b64encode(image_data.getvalue()).decode('utf-8')
        figure = f"data:image/png;base64,{figure}"
        return True, figure

    def __str__(self) -> str:
        extra_settings = {}
        if self.width is not None:
            extra_settings['width'] = self.width
        if self.height is not None:
            extra_settings['height'] = self.height
        was_pil, url = self._handle_pil_image(self.url)
        if was_pil:
            return f"<img src='{url}' {self.parse_extra_settings(**extra_settings)}>"
        url, external = self._handle_url(self.url)
        if not external:
            url = self.base_image_folder + url
        parsed_settings = self.parse_extra_settings(**extra_settings)
        return f"<img src='{url}' {parsed_settings}>"


@dataclass
class TextBox(PageContent):
    name: str
    kind: str
    default_value: str

    def __init__(self, name: str, default_value: str = None, kind: str = "text", **kwargs):
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
class TextArea(PageContent):
    name: str
    default_value: str
    EXTRA_ATTRS = ["rows", "cols", "autocomplete", "autofocus", "disabled", "placeholder", "readonly", "required"]

    def __init__(self, name: str, default_value: str = None, **kwargs):
        self.name = name
        self.default_value = default_value
        self.extra_settings = kwargs

    def __str__(self) -> str:
        parsed_settings = self.parse_extra_settings(**self.extra_settings)
        return f"<textarea name='{self.name}' {parsed_settings}>{self.default_value}</textarea>"


@dataclass
class SelectBox(PageContent):
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
        options = "\n".join(f"<option selected value='{option}'>{option}</option>"
                            if option == self.default_value else
                            f"<option value='{option}'>{option}</option>"
                            for option in self.options)
        return f"<select name='{self.name}' {parsed_settings}>{options}</select>"


@dataclass
class CheckBox(PageContent):
    EXTRA_ATTRS = ["checked"]
    name: str
    default_value: bool

    def __init__(self, name: str, default_value: bool = False, **kwargs):
        self.name = name
        self.default_value = default_value
        self.extra_settings = kwargs

    def __str__(self) -> str:
        parsed_settings = self.parse_extra_settings(**self.extra_settings)
        checked = 'checked' if self.default_value else ''
        return (f"<input type='hidden' name='{self.name}' value='' {parsed_settings}>"
                f"<input type='checkbox' name='{self.name}' {checked} value='checked' {parsed_settings}>")


@dataclass
class LineBreak(PageContent):
    def __str__(self) -> str:
        return "<br />"


@dataclass
class HorizontalRule(PageContent):
    def __str__(self) -> str:
        return "<hr />"


@dataclass
class Span(PageContent):
    def __init__(self, *args, **kwargs):
        self.content = args
        self.extra_settings = kwargs

    def __str__(self) -> str:
        parsed_settings = self.parse_extra_settings(**self.extra_settings)
        return f"<span {parsed_settings}>{''.join(str(item) for item in self.content)}</span>"


@dataclass
class Div(PageContent):
    def __init__(self, *args, **kwargs):
        self.content = args
        self.extra_settings = kwargs

    def __str__(self) -> str:
        parsed_settings = self.parse_extra_settings(**self.extra_settings)
        return f"<div {parsed_settings}>{''.join(str(item) for item in self.content)}</div>"


Division = Div
Box = Div


@dataclass
class Pre(PageContent):
    def __init__(self, *args, **kwargs):
        self.content = args
        self.extra_settings = kwargs

    def __str__(self) -> str:
        parsed_settings = self.parse_extra_settings(**self.extra_settings)
        return f"<pre {parsed_settings}>{''.join(str(item) for item in self.content)}</pre>"


PreformattedText = Pre


@dataclass
class Row(Div):
    def __init__(self, *args, **kwargs):
        self.content = args
        self.extra_settings = kwargs
        self.extra_settings['style_display'] = "flex"
        self.extra_settings['style_flex_direction'] = "row"
        self.extra_settings['style_align_items'] = "center"


@dataclass
class Button(PageContent, LinkContent):
    text: str
    url: str
    arguments: list[Argument]
    external: bool = False

    def __init__(self, text: str, url: str, arguments=None, **kwargs):
        self.text = text
        self.url, self.external = self._handle_url(url)
        self.extra_settings = kwargs
        self.arguments = arguments

    def __repr__(self):
        if self.arguments:
            return f"Button(text={self.text!r}, url={self.url!r}, arguments={self.arguments!r})"
        return f"Button(text={self.text!r}, url={self.url!r})"

    def __str__(self) -> str:
        precode = self.create_arguments(self.arguments, self.text)
        url = merge_url_query_params(self.url, {SUBMIT_BUTTON_KEY: self.text})
        parsed_settings = self.parse_extra_settings(**self.extra_settings)
        return f"{precode}<input type='submit' name='{SUBMIT_BUTTON_KEY}' value='{self.text}' formaction='{url}' {parsed_settings} />"


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

    def __init__(self, rows: list[list[str]], header=None, **kwargs):
        self.rows = rows
        self.header = header
        self.extra_settings = kwargs
        self.reformat_as_tabular()

    def reformat_as_single(self):
        result = []
        for field in fields(self.rows):
            value = getattr(self.rows, field.name)
            result.append(
                [f"<code>{html.escape(field.name)}</code>",
                 f"<code>{html.escape(field.type.__name__)}</code>",
                 f"<code>{html.escape(repr(value))}</code>"])
        self.rows = result
        if not self.header:
            self.header = ["Field", "Type", "Current Value"]

    def reformat_as_tabular(self):
        # print(self.rows, is_dataclass(self.rows))
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

    def __str__(self):
        return self.body


class MatPlotLibPlot(PageContent):
    args: tuple
    kwargs: dict

    def __init__(self, extra_matplotlib_settings=None, close_automatically=True, **kwargs):
        if not _has_matplotlib:
            raise ImportError("Matplotlib is not installed. Please install it to use this feature.")
        if extra_matplotlib_settings is None:
            extra_matplotlib_settings = {}
        self.extra_matplotlib_settings = extra_matplotlib_settings
        self.extra_settings = kwargs
        if "format" not in extra_matplotlib_settings:
            extra_matplotlib_settings["format"] = "png"
        if "bbox_inches" not in extra_matplotlib_settings:
            extra_matplotlib_settings["bbox_inches"] = "tight"
        self.close_automatically = close_automatically

    def __str__(self):
        parsed_settings = self.parse_extra_settings(**self.extra_settings)
        # Handle image processing
        image_data = io.BytesIO()
        plt.savefig(image_data, **self.extra_matplotlib_settings)
        if self.close_automatically:
            plt.close()
        image_data.seek(0)
        if self.extra_matplotlib_settings["format"] == "png":
            figure = base64.b64encode(image_data.getvalue()).decode('utf-8')
            figure = f"data:image/png;base64,{figure}"
            return f"<img src='{figure}' {parsed_settings}/>"
        elif self.extra_matplotlib_settings["format"] == "svg":
            figure = image_data.read().decode()
            return figure
        else:
            raise ValueError(f"Unsupported format {self.extra_matplotlib_settings['format']}")


@dataclass
class Download(PageContent):
    text: str
    filename: str
    content: str
    content_type: str = "text/plain"

    def __init__(self, text: str, filename: str, content: str, content_type: str = "text/plain"):
        self.text = text
        self.filename = filename
        self.content = content
        self.content_type = content_type

    def _handle_pil_image(self, image):
        if not HAS_PILLOW or isinstance(image, str):
            return False, image

        image_data = io.BytesIO()
        image.save(image_data, format="PNG")
        image_data.seek(0)
        figure = base64.b64encode(image_data.getvalue()).decode('utf-8')
        figure = f"data:image/png;base64,{figure}"
        return True, figure

    def __str__(self):
        was_pil, url = self._handle_pil_image(self.content)
        if was_pil:
            return f'<a download="{self.filename}" href="{url}">{self.text}</a>'
        return f'<a download="{self.filename}" href="data:{self.content_type},{self.content}">{self.text}</a>'


class FileUpload(PageContent):
    """
    A file upload component that allows users to upload files to the server.

    This works by creating a hidden input field that stores the file data as a JSON string.
    That input is sent, but the file data is not sent directly.

    The accept field can be used to specify the types of files that can be uploaded.
    It accepts either a literal string (e.g. "image/*") or a list of strings (e.g. ["image/png", "image/jpeg"]).
    You can either provide MIME types, extensions, or extensions without a period (e.g., "png", ".jpg").

    To have multiple files uploaded, use the `multiple` attribute, which will cause
    the corresponding parameter to be a list of files.
    """
    name: str
    EXTRA_ATTRS = ["accept", "capture", "multiple", "required"]

    def __init__(self, name: str, accept: Union[str, list[str]] = None, **kwargs):
        self.name = name
        self.extra_settings = kwargs

        # Parse accept options
        if accept is not None:
            if isinstance(accept, str):
                accept = [accept]
            accept= [f".{ext}" if "/" not in ext and not ext.startswith(".") else ext
                     for ext in accept]
            self.extra_settings['accept'] = ", ".join(accept)

    def __str__(self):
        parsed_settings = self.parse_extra_settings(**self.extra_settings)
        return f"<input type='file' name={self.name!r} {parsed_settings} />"
