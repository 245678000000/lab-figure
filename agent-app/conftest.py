"""Tests use a fixed copy of the ex vivo exclusion list (the real one lives outside the repo)."""
import os
import tempfile
from pathlib import Path

if not os.environ.get("AISI_EXCLUSIONS"):
    path = Path(tempfile.mkdtemp()) / "exvivo_sample_exclusions.tsv"
    path.write_text("canonical_sample_id\tgeo_sample_id\taliases\n"
                    "HNSCC3_HD\tGSM9266338_HNSCC3_HD\thnscc3.hd\n"
                    "HNSCC3_tumor\tGSM9266346_HNSCC3_T\tHNSCC3_T;hnscc3.t\n", encoding="utf-8")
    os.environ["AISI_EXCLUSIONS"] = str(path)
