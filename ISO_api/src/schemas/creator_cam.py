from typing import Literal

from pydantic import Field, model_validator

from src.schemas.creator import Identifier, StrictModel


class CamParseRequest(StrictModel):
    requestId: Identifier
    schemaHash: str = Field(pattern=r"^[a-f0-9]{64}$")
    rulesVersion: str
    workplanNodeId: Identifier
    camType: Literal["nx", "powermill"]
    orderedFileIds: list[Identifier] = Field(min_length=1, max_length=50)
    mappingFileId: Identifier | None = None

    @model_validator(mode="after")
    def unique_files(self):
        if len(set(self.orderedFileIds)) != len(self.orderedFileIds):
            raise ValueError("CAM file IDs must be unique")
        if self.mappingFileId in self.orderedFileIds:
            raise ValueError("Mapping file must have a separate ID")
        if self.camType == "nx" and len(self.orderedFileIds) != 1:
            raise ValueError("NX requires exactly one JSON file")
        return self
