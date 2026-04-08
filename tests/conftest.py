import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def xlsx_path():
    p = PROJECT_ROOT / "Atcare_Τιμοκατάλογος Συμπληρωμάτων Bio Tonics 2025.xlsx.xlsx"
    if not p.exists():
        pytest.skip(f"Supplier file not found: {p.name}")
    return p


@pytest.fixture(scope="session")
def biotonics_pdf_path():
    p = PROJECT_ROOT / "Atcare_Τιμοκατάλογος Συμπληρωμάτων Bio Tonics 2025.xlsx.pdf"
    if not p.exists():
        pytest.skip(f"Supplier file not found: {p.name}")
    return p


@pytest.fixture(scope="session")
def viogenesis_pdf_path():
    p = PROJECT_ROOT / "VioGenesis Product List November 2025.xlsx.pdf"
    if not p.exists():
        pytest.skip(f"Supplier file not found: {p.name}")
    return p
