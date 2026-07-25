"""
Unit tests for offline ECM sweep variant generation using idf_tools.
"""

import pytest
import os
import tempfile
from src.idf_tools.ecm_sweep import generate_ecm_variants


@pytest.fixture
def dummy_idf_file():
    fd, path = tempfile.mkstemp(suffix=".idf")
    content = """
Version, 26.2;
Building, Test Building, 0.0, Suburbs, 0.04, 0.4, FullExterior, 25;
Material, Roof Insulation, Smooth, 0.1, 0.04, 1400.0, 1000.0;
"""
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_generate_ecm_variants(dummy_idf_file):
    output_dir = tempfile.mkdtemp()
    ecm_defs = [
        {
            "name": "ecm_roof_insulation",
            "modifications": [
                {
                    "object_type": "Material",
                    "name": "Roof Insulation",
                    "fields": {"Thickness": 0.2},
                }
            ],
        }
    ]

    generated = generate_ecm_variants(
        baseline_idf_path=dummy_idf_file,
        ecm_definitions=ecm_defs,
        output_dir=output_dir,
    )

    assert len(generated) == 1
    assert os.path.exists(generated[0])
    with open(generated[0], "r", encoding="utf-8") as f:
        text = f.read()
    assert "ecm_roof_insulation" in text
