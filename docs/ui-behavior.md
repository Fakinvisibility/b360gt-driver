# UI media and playback behavior

## Media identification

The backend inspects file contents instead of trusting the file extension or
browser MIME type:

- still images are decoded by Pillow;
- animated images retain their embedded frame durations;
- video containers are inspected and decoded by PyAV.

## Import limits

Limits are selected from the detected media kind, not the filename extension:

- still images: 50 MiB;
- animated images: 200 MiB;
- videos: 256 MiB and 15 minutes;
- video containers: MP4, MOV, MKV, or WebM;
- video dimensions: at most 3840×2160 and 8,294,400 pixels per frame;
- source video rate: at most 120 FPS;
- still and animated image dimensions: at most 8192×8192 and 50,000,000
  pixels per frame.

Files with missing or invalid video duration/frame-rate metadata are rejected.
The first frame must also decode successfully when the preview is generated.
The library requires at least 1 GiB of free space to remain after import.

## Frame-rate policy

The UI deliberately exposes no frame-rate control.

- A still image is resent internally at 2 FPS. The display watchdog returns to
  the built-in logo when frame traffic stops, while 2 FPS leaves a conservative
  timing margin without wasting roughly 9 MiB/s on identical 480×480 frames.
- GIF/APNG timing comes from the media file.
- Video follows its source timestamps. Sources above 30 FPS are frame-dropped
  to at most 30 FPS without slowing playback.
- The internal watchdog refresh rate is capped at 30 FPS even for diagnostic
  command-line use.

This rate controls USB frame traffic, not the physical LCD scan rate. Increasing
it is not expected to improve image quality; it mainly increases USB and CPU
load.

## Preview shape and 480

The physical display canvas and protocol payload are 480 by 480 pixels. The
number 480 therefore describes both output width and output height, not FPS.

The preview uses a square with the same center-crop behavior as the encoder.
The empty preview shows only `请上传媒体文件`; resolution details appear after a
file is identified.

## Preview restoration

Uploading a file imports it into the persistent media library. Closing the
browser, restarting the UI server, or restarting the computer preserves:

- file name and detected media type;
- source and output resolution;
- image, GIF, or dynamic video preview;
- the most recently selected library item.

The default library directory is:

- Linux: `~/.local/share/b360gt/media`
- Windows: `%LOCALAPPDATA%\b360gt\media`

`B360GT_MEDIA_DIR` overrides the location. Each item has an isolated directory
containing its media file, metadata, and JPEG thumbnail. Deletion accepts only a
validated library ID and refuses item directories containing unknown files.
The UI plays only items in this managed library; arbitrary external filesystem
paths are intentionally not exposed.

## Dynamic video preview

Browser codec support is intentionally not used for the main video preview.
PyAV decodes the source and the local server emits a multipart JPEG stream at up
to 12 FPS. This allows MP4/WebM files supported by PyAV to animate in the
browser even when Chromium cannot decode the original codec.

The 12 FPS limit applies only to the control-panel preview. USB playback still
follows source timestamps up to the separate 30 FPS display limit.
