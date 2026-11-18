import os

from market_skew import seed


def _config(tmp_path):
    (tmp_path / "holdings.example.json").write_text("[]")
    (tmp_path / "watchlist.example.txt").write_text("# w\n")
    (tmp_path / "excluded.example.txt").write_text("# e\n")
    return tmp_path


def test_seed_creates_missing_files_from_examples(tmp_path):
    config = _config(tmp_path)
    made = seed.seed(config)
    assert sorted(made) == ["excluded.txt", "holdings.json", "watchlist.txt"]
    assert (config / "holdings.json").read_text() == "[]"
    assert (config / "watchlist.txt").read_text() == "# w\n"


def test_seed_never_overwrites_existing_files(tmp_path):
    config = _config(tmp_path)
    (config / "holdings.json").write_text('[{"symbol": "VOO"}]')
    made = seed.seed(config)
    assert "holdings.json" not in made
    assert (config / "holdings.json").read_text() == '[{"symbol": "VOO"}]'
    assert seed.seed(config) == []


def test_seed_skips_when_example_is_missing(tmp_path):
    assert seed.seed(tmp_path) == []


def test_local_env_sets_unset_keys_only(tmp_path, monkeypatch):
    monkeypatch.delenv("SKEW_TEST_A", raising=False)
    monkeypatch.setenv("SKEW_TEST_B", "kept")
    file = tmp_path / "local.env"
    file.write_text("# comment\nSKEW_TEST_A=\"one\"\nSKEW_TEST_B=other\nbad line\n")
    applied = seed.load_local_env(file)
    assert applied == {"SKEW_TEST_A": "one"}
    assert os.environ["SKEW_TEST_A"] == "one" and os.environ["SKEW_TEST_B"] == "kept"
    monkeypatch.delenv("SKEW_TEST_A")


def test_local_env_missing_file_is_fine(tmp_path):
    assert seed.load_local_env(tmp_path / "none.env") == {}
