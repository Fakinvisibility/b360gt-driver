"""Persistent, application-owned media library."""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .media import MediaInfo, inspect_media, render_preview_jpeg
from .media_policy import validate_media_import

ITEM_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
METADATA_NAME = "metadata.json"
PREVIEW_NAME = "preview.jpg"
STATE_NAME = "state.json"


def default_media_directory() -> Path:
    configured = os.environ.get("B360GT_MEDIA_DIR")
    if configured:
        return Path(configured).expanduser()

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / "b360gt" / "media"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home).expanduser() if xdg_data_home else Path.home() / ".local" / "share"
    return base / "b360gt" / "media"


@dataclass(frozen=True)
class LibraryItem:
    item_id: str
    name: str
    path: Path
    preview_path: Path
    size: int
    created_at: str
    media_info: MediaInfo

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.item_id,
            "name": self.name,
            "size": self.size,
            "created_at": self.created_at,
            "media_info": asdict(self.media_info),
        }


class MediaLibrary:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = (Path(root) if root is not None else default_media_directory()).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def add(
        self,
        source: str | Path,
        *,
        display_name: str,
        move: bool = False,
    ) -> LibraryItem:
        source_path = Path(source).resolve()
        if not source_path.is_file():
            raise ValueError(f"找不到待导入的媒体文件：{source_path}")

        info = inspect_media(source_path)
        validate_media_import(
            source_path,
            info,
            library_root=self.root,
            move=move,
        )
        preview = render_preview_jpeg(source_path)
        item_id = uuid.uuid4().hex
        suffix = Path(display_name).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,12}", suffix):
            suffix = source_path.suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,12}", suffix):
            suffix = ".media"

        temporary_dir = self.root / f"{item_id}.part"
        item_dir = self.root / item_id
        media_path = temporary_dir / f"media{suffix}"
        created_at = datetime.now(UTC).isoformat()
        metadata = {
            "id": item_id,
            "name": Path(display_name).name or f"media{suffix}",
            "file": media_path.name,
            "size": source_path.stat().st_size,
            "created_at": created_at,
            "media_info": asdict(info),
        }

        temporary_dir.mkdir()
        try:
            if move:
                shutil.move(str(source_path), str(media_path))
            else:
                shutil.copy2(source_path, media_path)
            (temporary_dir / PREVIEW_NAME).write_bytes(preview)
            (temporary_dir / METADATA_NAME).write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary_dir.replace(item_dir)
        except Exception:
            for child in (
                temporary_dir.iterdir() if temporary_dir.exists() else ()
            ):
                if child.is_file():
                    child.unlink(missing_ok=True)
            if temporary_dir.exists():
                temporary_dir.rmdir()
            raise

        return self.get(item_id)

    def list_items(self) -> list[LibraryItem]:
        items: list[LibraryItem] = []
        for directory in self.root.iterdir():
            resolved = directory.resolve()
            if (
                directory.is_dir()
                and ITEM_ID_PATTERN.fullmatch(directory.name)
                and resolved.parent == self.root
            ):
                try:
                    items.append(self._load(resolved))
                except (OSError, ValueError, KeyError, json.JSONDecodeError):
                    continue
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def get(self, item_id: str) -> LibraryItem:
        if not ITEM_ID_PATTERN.fullmatch(item_id):
            raise ValueError("媒体ID格式无效")
        directory = (self.root / item_id).resolve()
        if directory.parent != self.root or not directory.is_dir():
            raise ValueError("媒体库中不存在该文件")
        return self._load(directory)

    def delete(self, item_id: str) -> LibraryItem:
        item = self.get(item_id)
        directory = item.path.parent
        expected = {
            item.path.name,
            item.preview_path.name,
            METADATA_NAME,
        }
        actual = {child.name for child in directory.iterdir()}
        unexpected = actual - expected
        if unexpected:
            raise RuntimeError(
                f"媒体目录包含未知文件，拒绝删除：{', '.join(sorted(unexpected))}"
            )

        item.path.unlink(missing_ok=True)
        item.preview_path.unlink(missing_ok=True)
        (directory / METADATA_NAME).unlink(missing_ok=True)
        directory.rmdir()
        if self.selected_id() == item_id:
            self.remember_selected(None)
        return item

    def remember_selected(self, item_id: str | None) -> None:
        if item_id is not None:
            self.get(item_id)
        state_path = self.root / STATE_NAME
        temporary = self.root / f"{STATE_NAME}.part"
        temporary.write_text(
            json.dumps({"selected_id": item_id}, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(state_path)

    def selected_id(self) -> str | None:
        state_path = self.root / STATE_NAME
        if not state_path.is_file():
            return None
        try:
            value = json.loads(state_path.read_text(encoding="utf-8")).get("selected_id")
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, str) and ITEM_ID_PATTERN.fullmatch(value) else None

    def selected_item(self) -> LibraryItem | None:
        item_id = self.selected_id()
        if item_id is None:
            return None
        try:
            return self.get(item_id)
        except ValueError:
            return None

    def _load(self, directory: Path) -> LibraryItem:
        metadata = json.loads((directory / METADATA_NAME).read_text(encoding="utf-8"))
        if metadata["id"] != directory.name:
            raise ValueError("媒体元数据ID与目录不一致")
        media_path = (directory / metadata["file"]).resolve()
        if media_path.parent != directory or not media_path.is_file():
            raise ValueError("媒体文件路径无效")
        preview_path = (directory / PREVIEW_NAME).resolve()
        if preview_path.parent != directory or not preview_path.is_file():
            raise ValueError("媒体预览路径无效")
        info_data = metadata["media_info"]
        return LibraryItem(
            item_id=directory.name,
            name=str(metadata["name"]),
            path=media_path,
            preview_path=preview_path,
            size=int(metadata["size"]),
            created_at=str(metadata["created_at"]),
            media_info=MediaInfo(**info_data),
        )
