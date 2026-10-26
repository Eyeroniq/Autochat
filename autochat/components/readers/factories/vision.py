from autochat.components.readers.base_reader import IngestionReader
from autochat.components.readers.factories.base import ReaderFactory
from autochat.utils.dependencies import format_missing_dependency_message


class VisionReaderFactory(ReaderFactory):
    def create_reader(self, extension: str | None = None) -> IngestionReader:
        del extension

        try:
            from autochat.components.readers.vision.vision_reader import (
                VisionReader,
            )
        except ImportError as e:
            raise ImportError(
                format_missing_dependency_message(
                    "VisionReaderFactory requires additional dependencies that are not installed. "
                )
            ) from e

        return VisionReader(
            reader_settings=self.settings.transformation.vision_documents
        )
