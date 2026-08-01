#!/usr/bin/env python3
import os
import shutil
import tempfile
from pathlib import Path

from app.text_cleaner import ocisti_html_i_paragrafe, generiraj_inkrementalnu_putanju, TextCleaner
from app.file_manager import FileManager
from app.config_loader import load_global_config, save_settings


def test_text_cleaning():
    print("Testing text cleaner HTML & paragraph algorithm...")
    sirovi_tekst = (
        "First line of paragraph 1.<br/>Second line of paragraph 1.\r\n"
        "\r\n\r\n"
        "Paragraph 2 has\xa0hidden space\xa0and &nbsp; tags <span>like this</span>.\r\n"
        "  Still part of paragraph 2.  \r\n"
        "\r\n\r\n\r\n\r\n"
        "<p>Paragraph 3 after multiple blank lines.</p>"
    )

    expected = (
        "First line of paragraph 1. Second line of paragraph 1.\n\n"
        "Paragraph 2 has hidden space and &nbsp; tags like this. Still part of paragraph 2.\n\n"
        "Paragraph 3 after multiple blank lines."
    )

    clean = ocisti_html_i_paragrafe(sirovi_tekst)
    assert clean == expected, f"Cleaning mismatch!\n--- ACTUAL ---\n{clean}\n--- EXPECTED ---\n{expected}"
    print("[OK] Text cleaner HTML and paragraph normalization algorithm passed.")


def test_incremental_suffix_fixed():
    print("Testing [fixed] incremental suffix generation...")
    temp_dir = tempfile.mkdtemp()
    try:
        # Pass 1: Original non-existent -> Foundation [fixed].txt
        p1 = generiraj_inkrementalnu_putanju(temp_dir, "Foundation.txt", ".txt")
        assert os.path.basename(p1) == "Foundation [fixed].txt"
        with open(p1, "w", encoding="utf-8") as f:
            f.write("v1")

        # Pass 2: Foundation [fixed].txt exists -> Foundation [fixed]_001.txt
        p2 = generiraj_inkrementalnu_putanju(temp_dir, "Foundation.txt", ".txt")
        assert os.path.basename(p2) == "Foundation [fixed]_001.txt"
        with open(p2, "w", encoding="utf-8") as f:
            f.write("v2")

        # Pass 3: Foundation [fixed]_001.txt exists -> Foundation [fixed]_002.txt
        p3 = generiraj_inkrementalnu_putanju(temp_dir, "Foundation.txt", ".txt")
        assert os.path.basename(p3) == "Foundation [fixed]_002.txt"
        with open(p3, "w", encoding="utf-8") as f:
            f.write("v3")

        # Pass 4: Passing already fixed filename — no stacked [fixed]
        p4 = generiraj_inkrementalnu_putanju(temp_dir, "Foundation [fixed].txt", ".txt")
        assert os.path.basename(p4) == "Foundation [fixed]_003.txt"
        assert "[fixed] [fixed]" not in os.path.basename(p4)

        print("[OK] [fixed] incremental suffix generation passed.")
    finally:
        shutil.rmtree(temp_dir)


def test_unique_file_path_conversion():
    print("Testing FileManager.unique_file_path (conversion style)...")
    temp_dir = tempfile.mkdtemp()
    try:
        base = os.path.join(temp_dir, "01 Foundation - Isaac Asimov.txt")

        p1 = FileManager.unique_file_path(base)
        assert os.path.basename(p1) == "01 Foundation - Isaac Asimov.txt"
        with open(p1, "w", encoding="utf-8") as f:
            f.write("v1")

        p2 = FileManager.unique_file_path(base)
        assert os.path.basename(p2) == "01 Foundation - Isaac Asimov_001.txt"
        with open(p2, "w", encoding="utf-8") as f:
            f.write("v2")

        p3 = FileManager.unique_file_path(base)
        assert os.path.basename(p3) == "01 Foundation - Isaac Asimov_002.txt"
        with open(p3, "w", encoding="utf-8") as f:
            f.write("v3")

        # Ne gomilaj sufikse ako se prosljeđuje već sufiksirana putanja
        p4 = FileManager.unique_file_path(p2)
        assert os.path.basename(p4) == "01 Foundation - Isaac Asimov_003.txt"

        print("[OK] unique_file_path conversion-style passed.")
    finally:
        shutil.rmtree(temp_dir)


def test_unique_dir_path_audiobook():
    print("Testing FileManager.unique_dir_path (audiobook style)...")
    temp_dir = tempfile.mkdtemp()
    try:
        base = os.path.join(temp_dir, "01-Foundation---Isaac-Asimov")

        d1 = FileManager.unique_dir_path(base)
        assert d1 == os.path.normpath(base)
        os.makedirs(d1)

        d2 = FileManager.unique_dir_path(base)
        assert d2 == os.path.normpath(base + "_001")
        os.makedirs(d2)

        d3 = FileManager.unique_dir_path(base)
        assert d3 == os.path.normpath(base + "_002")

        # Stara mapa ostaje netaknuta
        assert os.path.isdir(base)
        assert os.listdir(base) == []

        print("[OK] unique_dir_path audiobook-style passed.")
    finally:
        shutil.rmtree(temp_dir)


def test_ensure_file_path_no_overwrite():
    print("Testing ensure_file_path never overwrites...")
    temp_dir = tempfile.mkdtemp()
    try:
        fm = FileManager({"directories": {}})
        target = Path(temp_dir) / "book.txt"
        target.write_text("original", encoding="utf-8")

        safe = fm.ensure_file_path(target, suffix_if_exists=True)
        assert safe != target
        assert safe.name == "book_001.txt"
        assert target.read_text(encoding="utf-8") == "original"

        print("[OK] ensure_file_path no-overwrite passed.")
    finally:
        shutil.rmtree(temp_dir)


def test_config_sort_mode():
    print("Testing config sort_mode load and save...")
    cfg = load_global_config()
    assert "sort_mode" in cfg
    original_mode = cfg["sort_mode"]

    cfg["sort_mode"] = "date_desc"
    save_settings(cfg)

    reloaded = load_global_config()
    assert reloaded.get("sort_mode") == "date_desc"

    cfg["sort_mode"] = original_mode
    save_settings(cfg)
    print("[OK] Sort mode persistence passed.")


if __name__ == "__main__":
    test_text_cleaning()
    test_incremental_suffix_fixed()
    test_unique_file_path_conversion()
    test_unique_dir_path_audiobook()
    test_ensure_file_path_no_overwrite()
    test_config_sort_mode()
    print("\nALL TEXT CLEANER & CLI TESTS PASSED!")
