from autochat.components.readers.base_reader import IngestionReader
from autochat.components.readers.factories.base import ReaderFactory
from autochat.utils.dependencies import format_missing_dependency_message


def _delimiter_reader() -> IngestionReader:
    try:
        from autochat.components.readers.text.delimiter_reader import (
            DelimiterTextReader,
        )
    except ImportError as e:
        raise ImportError(
            format_missing_dependency_message(
                "Delimited text reader",
            )
        ) from e
    return DelimiterTextReader()


def _email_reader() -> IngestionReader:
    try:
        from autochat.components.readers.text.email_reader import (
            EmailTextReader,
        )
    except ImportError as e:
        raise ImportError(
            format_missing_dependency_message(
                "Email reader",
            )
        ) from e
    return EmailTextReader()


def _html_reader() -> IngestionReader:
    try:
        from autochat.components.readers.text.html_reader import (
            HtmlReader,
        )
    except ImportError as e:
        raise ImportError(
            format_missing_dependency_message(
                "HTML reader",
                extras="ingest-markup",
            )
        ) from e
    return HtmlReader()


def _text_reader() -> IngestionReader:
    try:
        from autochat.components.readers.text.text_reader import (
            TextReader,
        )
    except ImportError as e:
        raise ImportError(
            format_missing_dependency_message(
                "Text reader",
            )
        ) from e
    return TextReader()


_EXTENSION_READERS = {
    ".csv": _delimiter_reader,
    ".tsv": _delimiter_reader,
    ".psv": _delimiter_reader,
    ".eml": _email_reader,
    ".html": _html_reader,
    ".htm": _html_reader,
    ".xhtml": _html_reader,
    ".xht": _html_reader,
    ".shtml": _html_reader,
    ".shtm": _html_reader,
    ".stm": _html_reader,
}


class TextReaderFactory(ReaderFactory):
    def create_reader(self, extension: str | None = None) -> IngestionReader:
        provider = _EXTENSION_READERS.get(extension) if extension else None
        return provider() if provider else _text_reader()
