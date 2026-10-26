from pydantic import Field

from autochat.components.readers.nodes.text_node import TextNode


class ChunkNode(TextNode):
    """Chunk tree node."""

    text_separator: str = Field(
        default="",
        description="Separator between text fields when converting to string.",
    )
