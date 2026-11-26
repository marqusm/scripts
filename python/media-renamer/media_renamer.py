import argparse
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from PIL import Image
from PIL.ExifTags import TAGS

logger = logging.getLogger(__name__)

# Constants
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
FILENAME_FORMAT = "%Y-%m-%d_%H-%M-%S"
CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
_config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
IMAGE_EXTENSIONS = set(_config["image_extensions"])
VIDEO_EXTENSIONS = set(_config["video_extensions"])
DEVICE_CODES = _config["device_codes"]
DATE_PATTERNS = [
    (re.compile(r"(\d{8}_\d{6})"), "%Y%m%d_%H%M%S"),
    (re.compile(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})"), "%Y-%m-%d_%H-%M-%S"),
    (re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}_\d{2}_\d{2})"), "%Y-%m-%d %H_%M_%S"),
]
TRASH_FILES = set(_config["trash_files"])
EXIF_IFD = 0x8769


# Enums
class MediaType(Enum):
    IMAGE = 'image'
    VIDEO = 'video'
    TRASH = 'trash'
    UNKNOWN = 'unknown'

class Mode(Enum):
    DRAFT = 'draft'
    EXECUTE = 'execute'

class Action(Enum):
    DELETE = 'delete'
    RENAME = 'rename'


# Classes
@dataclass
class Metadata:
    filename: str = ""
    extension: str = ""
    date_taken: datetime | None = None
    date_filename: datetime | None = None
    date_attr_created: datetime | None = None
    date_attr_modified: datetime | None = None
    date: datetime | None = None
    device: str = ""

@dataclass
class ActionResult:
    action: Action
    path: Path
    new_filename: str | None = None


# Functions
def main():
    start_time = datetime.now()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info(f"Starting script: {start_time.strftime(DATETIME_FORMAT)}")
    args = parse_arguments()
    logger.info(f"Args: {args}")
    mode = Mode.EXECUTE if args.execute else Mode.DRAFT
    default_device = args.device
    folder_path = get_folder_path(args.path)
    process_all_files(folder_path, mode, default_device, args.recursive)
    elapsed = datetime.now() - start_time
    logger.info(f"Script finished successfully in {elapsed.total_seconds():.1f}s")


def get_folder_path(folder_path: Path) -> Path:
    if not folder_path.exists() or not folder_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {folder_path}")
    return folder_path

def process_all_files(folder_path: Path, mode: Mode = Mode.DRAFT, default_device: str = "", recursive: bool = False):
    actions, skipped = collect_actions(folder_path, default_device, recursive)
    renamed, deleted, failed = execute_actions(actions, mode)
    logger.info(f"Summary: {renamed} renamed, {deleted} deleted, {skipped} skipped, {failed} failed")

def collect_actions(folder_path: Path, default_device: str = "", recursive: bool = False) -> tuple[list[ActionResult], int]:
    files = folder_path.rglob("*") if recursive else folder_path.iterdir()
    actions = []
    skipped = 0
    claimed: set[str] = set()  # target names already taken by earlier actions in this run
    for file in files:
        # Skip hidden/system dirs (.git, .Trashes, Synology @eaDir thumbnails).
        if any(part.startswith((".", "@")) for part in file.relative_to(folder_path).parts[:-1]):
            continue
        if file.is_file():
            action = process_file(file, default_device, claimed)
            if action is None:
                skipped += 1
            else:
                actions.append(action)
    return actions, skipped

def execute_actions(actions: list[ActionResult], mode: Mode) -> tuple[int, int, int]:
    renamed, deleted, failed = 0, 0, 0
    for action in actions:
        if perform_action(action, mode):
            if action.action == Action.RENAME:
                renamed += 1
            elif action.action == Action.DELETE:
                deleted += 1
        else:
            failed += 1
    return renamed, deleted, failed

def process_file(file_path: Path, default_device: str = "", claimed: set[str] | None = None) -> ActionResult | None:
    media_type = file_type(file_path)
    if media_type == MediaType.IMAGE:
        return rename_file(file_path, get_image_metadata(file_path, default_device), claimed)
    elif media_type == MediaType.VIDEO:
        return rename_file(file_path, get_video_metadata(file_path, default_device), claimed)
    elif media_type == MediaType.TRASH:
        return ActionResult(action=Action.DELETE, path=file_path)
    else:
        logger.info(f"Unsupported file type: {file_path}")
        return None

def rename_file(file_path: Path, metadata: Metadata, claimed: set[str] | None = None) -> ActionResult | None:
    """Pick a free target name. `claimed` holds targets already planned in this
    run (normcase'd full paths) so two files with the same timestamp don't
    both get the same name; the chosen target is added to it."""
    if claimed is None:
        claimed = set()
    base = f"{metadata.date.strftime(FILENAME_FORMAT)}{f'_{metadata.device}' if metadata.device else ''}"
    desired_filename = f"{base}{metadata.extension}"
    if desired_filename == metadata.filename:
        return None

    def taken(name: str) -> bool:
        target = file_path.parent / name
        if os.path.normcase(str(target)) in claimed:
            return True
        # On case-insensitive filesystems X.JPG "exists" as X.jpg; that is the
        # file itself (case-only rename), not a collision.
        return target.exists() and not target.samefile(file_path)

    counter = 1
    while taken(desired_filename) and desired_filename != metadata.filename:
        desired_filename = f"{base}_{counter}{metadata.extension}"
        counter += 1

    if desired_filename == metadata.filename:
        return None

    claimed.add(os.path.normcase(str(file_path.parent / desired_filename)))
    return ActionResult(action=Action.RENAME, path=file_path, new_filename=desired_filename)

def perform_action(result: ActionResult | None, mode: Mode = Mode.DRAFT) -> bool:
    if result is None:
        return True

    if result.action == Action.DELETE:
        logger.info(f"Delete: {result.path}")
        if mode == Mode.EXECUTE:
            try:
                result.path.unlink()
            except OSError as e:
                logger.warning(f"Failed to delete {result.path}: {e}")
                return False
    elif result.action == Action.RENAME:
        if result.new_filename is None:
            return True
        logger.info(f"Rename {result.path} -> {result.new_filename}")
        if mode == Mode.EXECUTE:
            new_file = result.path.parent / result.new_filename
            # POSIX rename() silently replaces an existing file; never overwrite.
            if new_file.exists() and not new_file.samefile(result.path):
                logger.warning(f"Failed to rename {result.path}: target exists: {new_file}")
                return False
            try:
                result.path.rename(new_file)
            except OSError as e:
                logger.warning(f"Failed to rename {result.path}: {e}")
                return False
    return True


# Helper functions
def utc_to_local(dt: datetime) -> datetime:
    """Video creation_time is UTC (MP4/QuickTime spec) while EXIF dates are
    local wall-clock time; convert so photos and videos line up. A naive
    value is taken as UTC too."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().replace(tzinfo=None)

def is_epoch(dt: datetime) -> bool:
    return dt.year == 1970

def calculate_date(meta: datetime | None, filename: datetime | None, attr_created: datetime, attr_modified: datetime) -> datetime:
    if meta and not is_epoch(meta):
        return meta
    if filename and not is_epoch(filename):
        return filename
    candidates: list[datetime] = []
    if not is_epoch(attr_created):
        candidates.append(attr_created)
    if not is_epoch(attr_modified):
        candidates.append(attr_modified)
    return min(candidates) if candidates else attr_modified

def get_date_from_filename(file_path: Path) -> datetime | None:
    filename = file_path.stem
    for pattern, fmt in DATE_PATTERNS:
        match = pattern.search(filename)
        if match:
            try:
                return datetime.strptime(match.group(1), fmt)
            except ValueError:
                continue
    return None

def get_device_code(device_name: str, default_device: str = "") -> str:
    if device_name == '':
        return default_device
    if device_name in DEVICE_CODES:
        return DEVICE_CODES[device_name]
    logger.warning(f"Unknown device name: {device_name}")
    return device_name

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        type=Path,
        help="Directory to process"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--draft", action="store_true", help="Run in draft mode (no changes)")
    group.add_argument("--execute", action="store_true", help="Perform real actions")
    parser.add_argument("--device", type=str, default="", help="Device suffix to use when not available in metadata")
    parser.add_argument("--recursive", action="store_true", help="Process subdirectories recursively")
    return parser.parse_args()

def file_type(file_path: Path) -> MediaType:
    ext = file_path.suffix.lower()
    # macOS AppleDouble metadata (._IMG_0042.jpg): junk, not a real image.
    if file_path.name.startswith("._"):
        return MediaType.TRASH
    if ext in IMAGE_EXTENSIONS:
        return MediaType.IMAGE
    elif ext in VIDEO_EXTENSIONS:
        return MediaType.VIDEO
    elif file_path.name in TRASH_FILES:
        return MediaType.TRASH
    else:
        return MediaType.UNKNOWN

def get_video_metadata(file_path: Path, default_device: str = "") -> Metadata:
    metadata = Metadata()
    metadata.filename = file_path.name
    metadata.extension = file_path.suffix.lower()
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(file_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        logger.warning(f"ffprobe not found, skipping metadata for {file_path.name}")
        metadata.device = default_device
        return resolve_dates(metadata, file_path)
    if result.stdout:
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning(f"Invalid ffprobe output for {file_path.name}")
            metadata.device = default_device
            return resolve_dates(metadata, file_path)
        if 'format' in data and 'tags' in data['format']:
            tags = data['format']['tags']
            if 'creation_time' in tags:
                try:
                    metadata.date_taken = utc_to_local(datetime.fromisoformat(tags['creation_time']))
                except ValueError:
                    logger.warning(f"Unexpected creation_time format: {tags['creation_time']}")
            # TODO: recheck the 'software' fallback. Some devices (e.g. Canon A60 -> "CanonMVI01")
            # only identify themselves there, but it often holds encoder/app strings like
            # "Lavf58.29.100", which then end up in the filename as an unknown device.
            device_name = tags.get('com.android.model') or tags.get('com.apple.quicktime.model') or tags.get('software')
            if device_name:
                metadata.device = get_device_code(device_name, default_device)
            else:
                metadata.device = default_device
    return resolve_dates(metadata, file_path)

def get_image_metadata(file_path: Path, default_device: str = "") -> Metadata:
    metadata = Metadata()
    metadata.filename = file_path.name
    metadata.extension = file_path.suffix.lower()
    exif_dict = {}
    try:
        with Image.open(file_path) as img:
            try:
                exif_data = img.getexif()
                if exif_data:
                    # getexif() only exposes IFD0 (Model etc.); cameras store
                    # DateTimeOriginal in the Exif sub-IFD, so merge that too.
                    for tag_id, value in (*exif_data.items(), *exif_data.get_ifd(EXIF_IFD).items()):
                        tag = TAGS.get(tag_id, tag_id)
                        exif_dict[tag] = value
            except (AttributeError, ValueError, OSError) as e:
                logger.warning(f"Error reading EXIF: {e}")
    except Exception as e:
        logger.warning(f"Failed to open image {file_path.name}: {e}")
    if 'DateTimeOriginal' in exif_dict:
        try:
            metadata.date_taken = datetime.strptime(exif_dict['DateTimeOriginal'], "%Y:%m:%d %H:%M:%S")
        except ValueError:
            logger.warning(f"Unexpected DateTimeOriginal format: {exif_dict['DateTimeOriginal']}")
    if 'Model' in exif_dict:
        metadata.device = get_device_code(exif_dict['Model'], default_device)
    else:
        metadata.device = default_device
    return resolve_dates(metadata, file_path)

def resolve_dates(metadata: Metadata, file_path: Path) -> Metadata:
    metadata.date_filename = get_date_from_filename(file_path)
    metadata.date_attr_created = datetime.fromtimestamp(file_path.stat().st_ctime)
    metadata.date_attr_modified = datetime.fromtimestamp(file_path.stat().st_mtime)
    metadata.date = calculate_date(metadata.date_taken, metadata.date_filename, metadata.date_attr_created, metadata.date_attr_modified)
    return metadata


if __name__ == "__main__":
    main()
