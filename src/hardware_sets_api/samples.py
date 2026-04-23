from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent.parent.parent / "demo_samples"


@dataclass
class SampleSpec:
    id: str
    name: str
    label: str
    filename: str

    @property
    def path(self) -> Path:
        return DEMO_DIR / self.filename


SAMPLES: list[SampleSpec] = [
    SampleSpec(id="sjc-div", name="SJC Division 08", label="List format", filename="SJC_Div_demo.pdf"),
    SampleSpec(id="morris-bank", name="Morris Bank", label="Tabular schedule", filename="morris_bank_demo.pdf"),
    SampleSpec(id="roselle-library", name="Roselle Public Library", label="Mixed format", filename="roselle_demo.pdf"),
]

SAMPLE_BY_ID: dict[str, SampleSpec] = {s.id: s for s in SAMPLES}
