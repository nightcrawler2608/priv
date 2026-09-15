"""Phase 3 tests: content-addressed raw HTML snapshots, offline (tmp_path)."""
from scrapers.books_toscrape.storage.raw_snapshots import save_raw_snapshot


def test_save_raw_snapshot_writes_file(tmp_path):
    path = save_raw_snapshot("<html>a</html>", page_num=1, snapshot_dir=tmp_path)
    assert path is not None
    assert path.read_text() == "<html>a</html>"


def test_save_raw_snapshot_skips_identical_content(tmp_path):
    first = save_raw_snapshot("<html>a</html>", page_num=1, snapshot_dir=tmp_path)
    second = save_raw_snapshot("<html>a</html>", page_num=1, snapshot_dir=tmp_path)

    assert first is not None
    assert second is None  # duplicate -- nothing new to store
    assert len(list(tmp_path.glob("page-1_*.html"))) == 1


def test_save_raw_snapshot_writes_new_file_when_content_changes(tmp_path):
    first = save_raw_snapshot("<html>a</html>", page_num=1, snapshot_dir=tmp_path)
    second = save_raw_snapshot("<html>b</html>", page_num=1, snapshot_dir=tmp_path)

    assert first != second
    assert second is not None
    assert len(list(tmp_path.glob("page-1_*.html"))) == 2
