# Media Renamer

## Description

A CLI tool that brings order to messy media libraries by renaming photo and video files into a consistent, date-based naming convention. Instead of dealing with cryptic camera-generated names like `IMG_20230415_093012.jpg` or `DSC_0042.jpg`, every file gets renamed to a uniform `YYYY-MM-DD_HH-MM-SS[_DEVICE].ext` format.

The tool reads the actual creation date from image EXIF data or video metadata (via ffprobe), falling back to filename patterns or file system timestamps when metadata is unavailable. It also identifies and removes junk files like `Thumbs.db`, `.DS_Store`, `desktop.ini`, and macOS `._*` AppleDouble files.

## Goals

- **Standardize filenames** across all media files using a consistent date-time format
- **Preserve origin info** by appending a device code (e.g. `A60` for Canon PowerShot A60) to the filename
- **Use the most accurate date** by prioritizing metadata over filename over file attributes
- **Safe by default** with a `--draft` mode that previews changes before any files are modified
- **Handle mixed media** by supporting both image and video files in a single pass


## Installation

Common Python installation
```bash
pip install -r requirements.txt
```

Using Python Launcher
```bash
py -m pip install -r requirements.txt
```


## Running
```bash
py media_renamer.py <path> [--draft|--execute]
```

| Argument      | Comment                                             |
|---------------|-----------------------------------------------------|
| path          | Directory to process (required)                     |
| --help        | Help                                                |
| --draft       | Draft mode                                          |
| --execute     | Writing mode                                        |
| --device CODE | Device suffix to use when not available in metadata |
| --recursive   | Process subdirectories recursively (skips hidden `.*` and `@*` dirs such as `.git`, Synology `@eaDir`) |

Example command could be:
```bash
py media_renamer.py /home/user/media/photos --execute
```


### Video timestamps

Video `creation_time` is stored as UTC and converted to the machine's local
time, so photos and videos line up. Some cameras write local time but label it
UTC; their videos will appear shifted by the timezone offset.


## Configuration

Device codes, file extensions, and trash files are configured in `config.json`:

| Key                | Description                                        |
|--------------------|----------------------------------------------------|
| `device_codes`     | Maps camera/phone model names to short codes       |
| `image_extensions` | File extensions treated as images                  |
| `video_extensions` | File extensions treated as videos                  |
| `trash_files`      | Filenames to delete (e.g. `Thumbs.db`, `.DS_Store`)|
