from pydantic import BaseModel, Field

from autochat.components.engines.citations.types import Citation


class AutoChatCitation(BaseModel):
    """AutoChatCitation represents a citation in the AutoChat format."""

    id: str | None = Field(
        default=None,
        description="Unique identifier for the citation",
    )
    index: int | None = Field(
        default=None,
        description="Index of the citation in the document",
    )
    artifact_id: str | None = Field(
        default=None,
        description="Identifier of the artifact associated with the citation",
    )
    source_id: str | None = Field(
        default=None,
        description="Identifier of the source document from which the citation is derived",
    )

    @classmethod
    def from_citation(cls, citation: Citation) -> "AutoChatCitation":
        return cls(
            id=citation.doc_id,
            index=citation.value.get("index") if citation.value else None,
            artifact_id=citation.value.get("artifact_id") if citation.value else None,
            source_id=citation.value.get("source_id") if citation.value else None,
        )

    @classmethod
    def to_citation(cls, autochat_citation: "AutoChatCitation") -> Citation:
        return Citation(
            text="",
            doc_id=autochat_citation.id,
            artifact_id=autochat_citation.artifact_id,
            source_id=autochat_citation.source_id,
            value={
                "index": autochat_citation.index,
                "artifact_id": autochat_citation.artifact_id,
                "source_id": autochat_citation.source_id,
            }
            if autochat_citation.index is not None
            else None,
        )
