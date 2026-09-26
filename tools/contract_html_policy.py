"""Narrow contract-fixture HTML checks, not the production HTML sanitizer.

The provider must sanitize/normalize before PUB freezes the payload. This
validator rejects unsupported markup; it never repairs an approved payload.
"""
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit


class ContractError(ValueError):
    """A bounded field/policy diagnostic; never include manuscript contents."""


TAGS = frozenset(
    "p h1 h2 h3 h4 h5 h6 blockquote pre code ul ol li strong em b i s del "
    "a br hr sup sub table caption thead tbody tfoot tr th td span".split()
)
VOID = frozenset({"br", "hr"})
ID = re.compile(r"cf-[a-z0-9][a-z0-9-]{0,95}\Z")
LANG = re.compile(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*\Z")


def validate_https_url(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ContractError("URL must be nonempty HTTPS text")
    if "\\" in value or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ContractError("URL contains whitespace or control characters")
    try:
        parts = urlsplit(value)
        if (
            parts.scheme != "https" or not parts.hostname
            or parts.username is not None or parts.password is not None
        ):
            raise ContractError("URL must be absolute HTTPS without userinfo")
        _ = parts.port
    except ValueError as exc:
        raise ContractError("URL is malformed") from exc


class _FixtureHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.ids: set[str] = set()
        self.targets: set[str] = set()

    def handle_starttag(self, tag, attrs):
        if tag not in TAGS:
            raise ContractError("rendered_html has an unsupported element")
        seen = set()
        for name, value in attrs:
            if name in seen or value is None:
                raise ContractError("rendered_html has duplicate/bare attributes")
            seen.add(name)
            if name == "id" and ID.fullmatch(value):
                if value in self.ids:
                    raise ContractError("rendered_html has duplicate heading IDs")
                self.ids.add(value)
            elif name == "lang" and LANG.fullmatch(value):
                pass
            elif tag == "a" and name == "href":
                if value.startswith("#") and ID.fullmatch(value[1:]):
                    self.targets.add(value[1:])
                else:
                    validate_https_url(value)
            elif tag == "a" and name == "title":
                pass
            elif tag == "code" and name == "class" and re.fullmatch(
                r"language-[A-Za-z0-9_+-]{1,40}", value
            ):
                pass
            elif tag == "ol" and name == "start" and re.fullmatch(r"[0-9]{1,6}", value):
                pass
            elif tag in {"th", "td"} and name in {"colspan", "rowspan"} and re.fullmatch(
                r"[1-9][0-9]?", value
            ):
                pass
            else:
                raise ContractError("rendered_html has an unsupported attribute")
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise ContractError("rendered_html must have explicit balanced closing tags")

    def handle_startendtag(self, tag, attrs):
        if tag not in VOID:
            raise ContractError("only br/hr may be self-closing")
        self.handle_starttag(tag, attrs)

    def handle_comment(self, data):
        raise ContractError("rendered_html comments are not allowed")

    def handle_decl(self, decl):
        raise ContractError("rendered_html declarations are not allowed")

    def handle_pi(self, data):
        raise ContractError("rendered_html processing instructions are not allowed")

    def unknown_decl(self, data):
        raise ContractError("rendered_html declarations are not allowed")


def validate_fixture_html(value: str) -> None:
    parser = _FixtureHTML()
    try:
        parser.feed(value)
        parser.close()
    except (AssertionError, ValueError) as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError("rendered_html cannot be parsed") from exc
    if parser.stack:
        raise ContractError("rendered_html has unclosed elements")
    if parser.targets - parser.ids:
        raise ContractError("rendered_html has an unresolved local fragment")
