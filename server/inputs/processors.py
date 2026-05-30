from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProcessedInput:
    text: str
    modality: str = "text"


class InputProcessor(Protocol):
    def process(self, raw: str) -> ProcessedInput:
        ...


class TextProcessor:
    def process(self, raw: str) -> ProcessedInput:
        return ProcessedInput(text=raw.strip(), modality="text")


class ASRProcessor:
    def process(self, raw: str) -> ProcessedInput:
        raise NotImplementedError("ASRProcessor is reserved for voice input.")


class VLMProcessor:
    def process(self, raw: str) -> ProcessedInput:
        raise NotImplementedError("VLMProcessor is reserved for image input.")
