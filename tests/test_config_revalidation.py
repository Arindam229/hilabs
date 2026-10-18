from pathlib import Path

from pipeline.config import load_config


def test_revalidation_zip_env_override_is_resolved_as_absolute_path(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "data_dir: data\n"
        "sources:\n"
        "  archive: source.zip\n"
        "  revalidation_zip: configured.zip\n"
    )
    override = tmp_path / "downloaded-revalidation.zip"
    monkeypatch.setenv("PTD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PTD_REVALIDATION_ZIP", str(override))

    cfg = load_config(config_path)

    assert cfg.revalidation_zip == Path(override)
