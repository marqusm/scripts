import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

import media_renamer

pytestmark = pytest.mark.filterwarnings("default")

@pytest.fixture(autouse=True)
def _capture_logs(caplog):
    with caplog.at_level(logging.INFO, logger="media_renamer"):
        yield


# --- process_file routing tests ---

def test_process_file_image_returns_action_result(monkeypatch, tmp_path):
    dummy_path = tmp_path / "photo.jpg"
    dummy_path.write_text("x")

    fake_metadata = media_renamer.Metadata(filename="photo.jpg", extension=".jpg", date=datetime(2023, 1, 1), device="X")
    expected = media_renamer.ActionResult(action=media_renamer.Action.RENAME, path=dummy_path, new_filename="new.jpg")
    monkeypatch.setattr(media_renamer, "file_type", lambda _p: media_renamer.MediaType.IMAGE)
    monkeypatch.setattr(media_renamer, "get_image_metadata", lambda _p, _d="": fake_metadata)
    monkeypatch.setattr(media_renamer, "rename_file", lambda _p, _m, _c=None: expected)

    result = media_renamer.process_file(dummy_path)
    assert result == expected


def test_process_file_video_returns_action_result(monkeypatch, tmp_path):
    dummy_path = tmp_path / "video.mp4"
    dummy_path.write_text("x")

    fake_metadata = media_renamer.Metadata(filename="video.mp4", extension=".mp4", date=datetime(2023, 1, 1), device="X")
    expected = media_renamer.ActionResult(action=media_renamer.Action.RENAME, path=dummy_path, new_filename="new.mp4")
    monkeypatch.setattr(media_renamer, "file_type", lambda _p: media_renamer.MediaType.VIDEO)
    monkeypatch.setattr(media_renamer, "get_video_metadata", lambda _p, _d="": fake_metadata)
    monkeypatch.setattr(media_renamer, "rename_file", lambda _p, _m, _c=None: expected)

    result = media_renamer.process_file(dummy_path)
    assert result == expected


def test_process_file_trash_returns_action_result(monkeypatch, tmp_path):
    dummy_path = tmp_path / "Thumbs.db"
    dummy_path.write_text("x")

    monkeypatch.setattr(media_renamer, "file_type", lambda _p: media_renamer.MediaType.TRASH)

    result = media_renamer.process_file(dummy_path)
    assert result == media_renamer.ActionResult(action=media_renamer.Action.DELETE, path=dummy_path)


def test_process_file_unknown_returns_none(monkeypatch, tmp_path, caplog):
    dummy_path = tmp_path / "file.bin"
    dummy_path.write_text("x")

    monkeypatch.setattr(media_renamer, "file_type", lambda _p: media_renamer.MediaType.UNKNOWN)
    result = media_renamer.process_file(dummy_path)

    assert result is None
    assert "Unsupported file type" in caplog.text


# --- file_type tests ---

def test_file_type_image():
    assert media_renamer.file_type(Path("photo.jpg")) == media_renamer.MediaType.IMAGE
    assert media_renamer.file_type(Path("photo.JPEG")) == media_renamer.MediaType.IMAGE
    assert media_renamer.file_type(Path("photo.png")) == media_renamer.MediaType.IMAGE


def test_file_type_video():
    assert media_renamer.file_type(Path("video.mp4")) == media_renamer.MediaType.VIDEO
    assert media_renamer.file_type(Path("video.MOV")) == media_renamer.MediaType.VIDEO


def test_file_type_trash():
    assert media_renamer.file_type(Path("Thumbs.db")) == media_renamer.MediaType.TRASH
    assert media_renamer.file_type(Path(".DS_Store")) == media_renamer.MediaType.TRASH
    assert media_renamer.file_type(Path("desktop.ini")) == media_renamer.MediaType.TRASH


def test_file_type_unknown():
    assert media_renamer.file_type(Path("notes.txt")) == media_renamer.MediaType.UNKNOWN


# --- calculate_date tests ---

def test_calculate_date_prefers_meta():
    meta = datetime(2020, 1, 1)
    filename = datetime(2021, 1, 1)
    created = datetime(2022, 1, 1)
    modified = datetime(2019, 1, 1)
    result = media_renamer.calculate_date(meta, filename, created, modified)
    assert result == meta


def test_calculate_date_falls_back_to_filename():
    filename = datetime(2019, 1, 1)
    created = datetime(2022, 1, 1)
    modified = datetime(2021, 1, 1)
    result = media_renamer.calculate_date(None, filename, created, modified)
    assert result == filename


def test_calculate_date_prefers_filename_over_older_attrs():
    filename = datetime(2023, 1, 1)
    created = datetime(2018, 1, 1)
    modified = datetime(2019, 1, 1)
    result = media_renamer.calculate_date(None, filename, created, modified)
    assert result == filename


def test_calculate_date_uses_modified_when_older():
    created = datetime(2022, 1, 1)
    modified = datetime(2019, 1, 1)
    result = media_renamer.calculate_date(None, None, created, modified)
    assert result == modified


def test_calculate_date_uses_created_when_older():
    created = datetime(2019, 1, 1)
    modified = datetime(2022, 1, 1)
    result = media_renamer.calculate_date(None, None, created, modified)
    assert result == created


# --- get_date_from_filename tests ---

def test_get_date_from_filename_yyyymmdd_hhmmss():
    result = media_renamer.get_date_from_filename(Path("20230415_093012.jpg"))
    assert result == datetime(2023, 4, 15, 9, 30, 12)


def test_get_date_from_filename_dashed_format():
    result = media_renamer.get_date_from_filename(Path("2023-04-15_09-30-12.jpg"))
    assert result == datetime(2023, 4, 15, 9, 30, 12)


def test_get_date_from_filename_no_match():
    result = media_renamer.get_date_from_filename(Path("random_name.jpg"))
    assert result is None


# --- get_device_code tests ---

def test_get_device_code_known():
    assert media_renamer.get_device_code('Canon PowerShot A60') == 'A60'
    assert media_renamer.get_device_code('CanonMVI01') == 'A60'


def test_get_device_code_empty():
    assert media_renamer.get_device_code('') == ''


def test_get_device_code_unknown(caplog):
    result = media_renamer.get_device_code('Nikon D3500')
    assert result == 'Nikon D3500'
    assert "Unknown device name" in caplog.text


def test_get_device_code_empty_with_custom_default():
    assert media_renamer.get_device_code('', 'MyDevice') == 'MyDevice'


# --- rename_file tests ---

def test_rename_file_returns_action_when_name_differs(tmp_path):
    file_path = tmp_path / "old_name.jpg"
    file_path.write_text("x")
    metadata = media_renamer.Metadata(
        filename="old_name.jpg",
        extension=".jpg",
        date=datetime(2023, 4, 15, 9, 30, 12),
        device="CA60",
    )
    result = media_renamer.rename_file(file_path, metadata)
    assert result is not None
    assert result.action == media_renamer.Action.RENAME
    assert result.new_filename == "2023-04-15_09-30-12_CA60.jpg"


def test_rename_file_returns_none_when_name_matches(tmp_path):
    file_path = tmp_path / "2023-04-15_09-30-12.jpg"
    file_path.write_text("x")
    metadata = media_renamer.Metadata(
        filename="2023-04-15_09-30-12.jpg",
        extension=".jpg",
        date=datetime(2023, 4, 15, 9, 30, 12),
        device="",
    )
    result = media_renamer.rename_file(file_path, metadata)
    assert result is None


def test_rename_file_without_device(tmp_path):
    file_path = tmp_path / "old.jpg"
    file_path.write_text("x")
    metadata = media_renamer.Metadata(
        filename="old.jpg",
        extension=".jpg",
        date=datetime(2023, 4, 15, 9, 30, 12),
        device="",
    )
    result = media_renamer.rename_file(file_path, metadata)
    assert result is not None
    assert result.new_filename == "2023-04-15_09-30-12.jpg"


def test_rename_file_handles_collision(tmp_path):
    file_path = tmp_path / "old.jpg"
    file_path.write_text("x")
    (tmp_path / "2023-04-15_09-30-12_S24.jpg").write_text("x")
    metadata = media_renamer.Metadata(
        filename="old.jpg",
        extension=".jpg",
        date=datetime(2023, 4, 15, 9, 30, 12),
        device="S24",
    )
    result = media_renamer.rename_file(file_path, metadata)
    assert result is not None
    assert result.new_filename == "2023-04-15_09-30-12_S24_1.jpg"


def test_rename_file_handles_multiple_collisions(tmp_path):
    file_path = tmp_path / "old.jpg"
    file_path.write_text("x")
    (tmp_path / "2023-04-15_09-30-12_S24.jpg").write_text("x")
    (tmp_path / "2023-04-15_09-30-12_S24_1.jpg").write_text("x")
    metadata = media_renamer.Metadata(
        filename="old.jpg",
        extension=".jpg",
        date=datetime(2023, 4, 15, 9, 30, 12),
        device="S24",
    )
    result = media_renamer.rename_file(file_path, metadata)
    assert result is not None
    assert result.new_filename == "2023-04-15_09-30-12_S24_2.jpg"


def test_rename_file_avoids_names_claimed_in_same_run(tmp_path):
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    a.write_text("x")
    b.write_text("x")
    claimed = set()
    meta = lambda name: media_renamer.Metadata(
        filename=name, extension=".jpg", date=datetime(2023, 4, 15, 9, 30, 12), device="S24")
    ra = media_renamer.rename_file(a, meta("a.jpg"), claimed)
    rb = media_renamer.rename_file(b, meta("b.jpg"), claimed)
    assert ra.new_filename == "2023-04-15_09-30-12_S24.jpg"
    assert rb.new_filename == "2023-04-15_09-30-12_S24_1.jpg"


def test_collect_and_execute_same_timestamp_keeps_both_files(tmp_path, monkeypatch):
    for name in ("a.jpg", "b.jpg"):
        (tmp_path / name).write_text(name)
    monkeypatch.setattr(media_renamer, "get_image_metadata", lambda p, _d="": media_renamer.Metadata(
        filename=p.name, extension=".jpg", date=datetime(2023, 4, 15, 9, 30, 12), device="S24"))

    actions, _ = media_renamer.collect_actions(tmp_path)
    renamed, _, failed = media_renamer.execute_actions(actions, media_renamer.Mode.EXECUTE)
    assert (renamed, failed) == (2, 0)
    assert sorted(p.read_text() for p in tmp_path.iterdir()) == ["a.jpg", "b.jpg"]


def test_rename_file_case_only_extension_is_not_a_collision(tmp_path):
    f = tmp_path / "2023-04-15_09-30-12_S24.JPG"
    f.write_text("x")
    meta = media_renamer.Metadata(
        filename=f.name, extension=".jpg", date=datetime(2023, 4, 15, 9, 30, 12), device="S24")
    result = media_renamer.rename_file(f, meta)
    assert result.new_filename == "2023-04-15_09-30-12_S24.jpg"
    assert media_renamer.perform_action(result, media_renamer.Mode.EXECUTE) is True
    assert [p.name for p in tmp_path.iterdir()] == ["2023-04-15_09-30-12_S24.jpg"]


def test_file_type_appledouble_is_trash():
    assert media_renamer.file_type(Path("._IMG_0042.jpg")) == media_renamer.MediaType.TRASH


def test_collect_actions_recursive_skips_hidden_and_system_dirs(tmp_path, monkeypatch):
    for d in (".git", "@eaDir", "sub"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "a.jpg").write_text("x")
    monkeypatch.setattr(media_renamer, "get_image_metadata", lambda p, _d="": media_renamer.Metadata(
        filename=p.name, extension=".jpg", date=datetime(2023, 4, 15, 9, 30, 12)))

    actions, _ = media_renamer.collect_actions(tmp_path, recursive=True)
    assert [a.path.parent.name for a in actions] == ["sub"]


# --- perform_action tests ---

def test_perform_action_execute_refuses_to_overwrite(tmp_path):
    src = tmp_path / "old.jpg"
    src.write_text("src")
    (tmp_path / "new.jpg").write_text("existing")
    result = media_renamer.ActionResult(action=media_renamer.Action.RENAME, path=src, new_filename="new.jpg")
    assert media_renamer.perform_action(result, media_renamer.Mode.EXECUTE) is False
    assert src.exists()
    assert (tmp_path / "new.jpg").read_text() == "existing"


def test_perform_action_draft_prints_rename(caplog):
    result = media_renamer.ActionResult(action=media_renamer.Action.RENAME, path=Path("/tmp/old.jpg"), new_filename="new.jpg")
    assert media_renamer.perform_action(result, media_renamer.Mode.DRAFT) is True
    assert "Rename" in caplog.text


def test_perform_action_draft_prints_delete(caplog):
    result = media_renamer.ActionResult(action=media_renamer.Action.DELETE, path=Path("/tmp/file.db"))
    assert media_renamer.perform_action(result, media_renamer.Mode.DRAFT) is True
    assert "Delete" in caplog.text


def test_perform_action_execute_renames(tmp_path):
    file_path = tmp_path / "old.jpg"
    file_path.write_text("x")
    result = media_renamer.ActionResult(action=media_renamer.Action.RENAME, path=file_path, new_filename="new.jpg")
    assert media_renamer.perform_action(result, media_renamer.Mode.EXECUTE) is True
    assert not file_path.exists()
    assert (tmp_path / "new.jpg").exists()


def test_perform_action_execute_deletes(tmp_path):
    file_path = tmp_path / "Thumbs.db"
    file_path.write_text("x")
    result = media_renamer.ActionResult(action=media_renamer.Action.DELETE, path=file_path)
    assert media_renamer.perform_action(result, media_renamer.Mode.EXECUTE) is True
    assert not file_path.exists()


def test_perform_action_none_is_noop():
    assert media_renamer.perform_action(None, media_renamer.Mode.EXECUTE) is True


def test_perform_action_execute_rename_failure(tmp_path):
    file_path = tmp_path / "nonexistent.jpg"
    result = media_renamer.ActionResult(action=media_renamer.Action.RENAME, path=file_path, new_filename="new.jpg")
    assert media_renamer.perform_action(result, media_renamer.Mode.EXECUTE) is False


def test_perform_action_execute_delete_failure(tmp_path):
    file_path = tmp_path / "nonexistent.db"
    result = media_renamer.ActionResult(action=media_renamer.Action.DELETE, path=file_path)
    assert media_renamer.perform_action(result, media_renamer.Mode.EXECUTE) is False


# --- collect_actions tests ---

def test_collect_actions_groups_by_type(tmp_path, monkeypatch):
    img = Image.new('RGB', (1, 1), color='red')
    img.save(str(tmp_path / "20230415_093012.jpg"))
    (tmp_path / "Thumbs.db").write_text("x")
    (tmp_path / "notes.txt").write_text("x")

    monkeypatch.setattr(media_renamer.subprocess, "run", lambda *_, **__: MagicMock(stdout=""))

    actions, skipped = media_renamer.collect_actions(tmp_path)
    assert skipped == 1
    action_types = {a.action for a in actions}
    assert media_renamer.Action.RENAME in action_types
    assert media_renamer.Action.DELETE in action_types


# --- execute_actions tests ---

def test_execute_actions_counts_results(tmp_path):
    file_to_rename = tmp_path / "old.jpg"
    file_to_rename.write_text("x")
    file_to_delete = tmp_path / "Thumbs.db"
    file_to_delete.write_text("x")

    actions = [
        media_renamer.ActionResult(action=media_renamer.Action.RENAME, path=file_to_rename, new_filename="new.jpg"),
        media_renamer.ActionResult(action=media_renamer.Action.DELETE, path=file_to_delete),
        media_renamer.ActionResult(action=media_renamer.Action.RENAME, path=tmp_path / "nonexistent.jpg", new_filename="x.jpg"),
    ]
    renamed, deleted, failed = media_renamer.execute_actions(actions, media_renamer.Mode.EXECUTE)
    assert renamed == 1
    assert deleted == 1
    assert failed == 1


# --- recursive tests ---

def test_collect_actions_recursive(tmp_path, monkeypatch):
    subdir = tmp_path / "sub"
    subdir.mkdir()
    img = Image.new('RGB', (1, 1), color='red')
    img.save(str(tmp_path / "20230415_093012.jpg"))
    img.save(str(subdir / "20230101_120000.jpg"))

    monkeypatch.setattr(media_renamer.subprocess, "run", lambda *_, **__: MagicMock(stdout=""))

    actions_flat, _ = media_renamer.collect_actions(tmp_path, recursive=False)
    actions_recursive, _ = media_renamer.collect_actions(tmp_path, recursive=True)
    assert len(actions_recursive) > len(actions_flat)


# --- process_all_files tests ---

def test_process_all_files_prints_summary(tmp_path, caplog, monkeypatch):
    img = Image.new('RGB', (1, 1), color='red')
    img.save(str(tmp_path / "20230415_093012.jpg"))
    (tmp_path / "Thumbs.db").write_text("x")
    (tmp_path / "notes.txt").write_text("x")

    monkeypatch.setattr(media_renamer.subprocess, "run", lambda *_, **__: MagicMock(stdout=""))

    media_renamer.process_all_files(tmp_path)
    assert "Summary:" in caplog.text


# --- get_image_metadata tests ---

def test_get_image_metadata_reads_exif(tmp_path):
    file_path = tmp_path / "photo.jpg"
    img = Image.new('RGB', (1, 1), color='red')
    exif = img.getexif()
    exif[0x0110] = "Canon PowerShot A60"      # Model (IFD0)
    # DateTimeOriginal lives in the Exif sub-IFD, as real cameras write it.
    exif.get_ifd(media_renamer.EXIF_IFD)[0x9003] = "2004:07:17 10:15:30"
    img.save(str(file_path), exif=exif.tobytes())

    metadata = media_renamer.get_image_metadata(file_path)
    assert metadata.filename == "photo.jpg"
    assert metadata.extension == ".jpg"
    assert metadata.date_taken == datetime(2004, 7, 17, 10, 15, 30)
    assert metadata.device == "A60"
    assert metadata.date == datetime(2004, 7, 17, 10, 15, 30)


def test_get_image_metadata_falls_back_to_filename_date(tmp_path):
    file_path = tmp_path / "20230415_093012.jpg"
    img = Image.new('RGB', (1, 1), color='red')
    img.save(str(file_path))

    metadata = media_renamer.get_image_metadata(file_path)
    assert metadata.date == datetime(2023, 4, 15, 9, 30, 12)


# --- get_video_metadata tests ---

def test_get_video_metadata_no_ffprobe(tmp_path, monkeypatch):
    file_path = tmp_path / "20230415_093012.mp4"
    file_path.write_text("fake video")

    mock_result = MagicMock()
    mock_result.stdout = ""
    monkeypatch.setattr(media_renamer.subprocess, "run", lambda *_, **__: mock_result)

    metadata = media_renamer.get_video_metadata(file_path)
    assert metadata.filename == "20230415_093012.mp4"
    assert metadata.extension == ".mp4"
    assert metadata.date == datetime(2023, 4, 15, 9, 30, 12)


def test_get_video_metadata_with_ffprobe_data(tmp_path, monkeypatch):
    file_path = tmp_path / "video.mp4"
    file_path.write_text("fake video")

    mock_result = MagicMock()
    mock_result.stdout = '{"format": {"tags": {"creation_time": "2023-06-01T14:30:00.000000Z", "software": "Canon PowerShot A60"}}}'
    monkeypatch.setattr(media_renamer.subprocess, "run", lambda *_, **__: mock_result)

    metadata = media_renamer.get_video_metadata(file_path)
    expected = datetime(2023, 6, 1, 14, 30, 0, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    assert metadata.date_taken == expected
    assert metadata.device == "A60"
    assert metadata.date == expected


def test_utc_to_local_converts_and_accepts_no_fraction():
    aware = datetime(2023, 6, 1, 14, 30, tzinfo=timezone.utc)
    local = aware.astimezone().replace(tzinfo=None)
    assert media_renamer.utc_to_local(datetime.fromisoformat("2023-06-01T14:30:00Z")) == local
    assert media_renamer.utc_to_local(datetime(2023, 6, 1, 14, 30)) == local


def test_get_video_metadata_ffprobe_missing(tmp_path, monkeypatch):
    file_path = tmp_path / "20230415_093012.mp4"
    file_path.write_text("fake video")

    def raise_fnf(*_, **__):
        raise FileNotFoundError("ffprobe not found")
    monkeypatch.setattr(media_renamer.subprocess, "run", raise_fnf)

    metadata = media_renamer.get_video_metadata(file_path)
    assert metadata.date == datetime(2023, 4, 15, 9, 30, 12)
