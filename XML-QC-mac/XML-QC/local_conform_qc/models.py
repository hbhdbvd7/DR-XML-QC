"""Shared data models for the local conform QC tool."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Issue:
    """A structured issue that can be written to reports."""

    code: str
    severity: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolConfig:
    """Runtime paths and options selected by GUI or CLI."""

    project_root: Path | None = None
    xml_paths: list[Path] = field(default_factory=list)
    media_root: Path | None = None
    look_references: list[Path] = field(default_factory=list)
    project_name: str | None = None
    import_all_media: bool = False


@dataclass(slots=True)
class XmlClip:
    """A clip item extracted from an xmeml file."""

    index: int
    clip_id: str
    name: str
    start: int | None
    end: int | None
    duration: int | None
    source_in: int | None
    source_out: int | None
    pathurl: str
    decoded_path: str
    timebase: int | None
    file_timebase: int | None
    track_index: int | None = None


@dataclass(slots=True)
class XmlPrecheckResult:
    """Parsed xmeml clips and precheck issues."""

    xml_path: Path
    sequence_name: str
    sequence_timebase: int | None = None
    clips: list[XmlClip] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


@dataclass(slots=True)
class MediaFile:
    """A media file discovered under the selected project root."""

    path: Path
    name_key: str
    stem_key: str


@dataclass(slots=True)
class MediaMatch:
    """The result of matching one XML clip to local media."""

    clip: XmlClip
    status: str
    candidates: list[Path] = field(default_factory=list)
    selected_path: Path | None = None
    issues: list[Issue] = field(default_factory=list)


@dataclass(slots=True)
class ResolveImportAttempt:
    """One Resolve XML import attempt and observed result."""

    attempt: int
    options: dict[str, Any]
    success: bool
    result_type: str
    result_repr: str
    current_timeline_name: str | None = None
    error: str | None = None


@dataclass(slots=True)
class ResolveImportResult:
    """Summary of media, reference, and XML imports into Resolve."""

    project_name: str
    folders: dict[str, str] = field(default_factory=dict)
    imported_media: list[str] = field(default_factory=list)
    imported_ref_media: list[str] = field(default_factory=list)
    imported_offline_references: list[str] = field(default_factory=list)
    imported_look_references: list[str] = field(default_factory=list)
    xml_import_attempts: list[ResolveImportAttempt] = field(default_factory=list)
    timeline_name: str | None = None
    issues: list[Issue] = field(default_factory=list)


@dataclass(slots=True)
class TimelineItemRecord:
    """A video timeline item read back from Resolve."""

    track_type: str
    track_index: int
    item_index: int
    name: str
    start: int | None = None
    end: int | None = None
    duration: int | None = None
    source_start: int | None = None
    source_end: int | None = None
    left_offset: int | None = None
    right_offset: int | None = None
    media_pool_name: str | None = None
    media_file_path: str | None = None
    is_offline: bool = False
    properties: dict[str, Any] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)


@dataclass(slots=True)
class TimelineReadbackResult:
    """Timeline item readback data for later QC and reports."""

    timeline_name: str
    track_counts: dict[str, int] = field(default_factory=dict)
    video_items: list[TimelineItemRecord] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


@dataclass(slots=True)
class ClipComparison:
    """One XML clip compared with one Resolve timeline item."""

    track_index: int
    item_index: int
    xml_clip_index: int | None = None
    timeline_item_index: int | None = None
    xml_name: str | None = None
    timeline_name: str | None = None
    status: str = "not_checked"
    issues: list[Issue] = field(default_factory=list)


@dataclass(slots=True)
class ConformQcResult:
    """Structured conform QC output for reports."""

    status: str
    summary: dict[str, Any] = field(default_factory=dict)
    comparisons: list[ClipComparison] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


@dataclass(slots=True)
class ReportData:
    """Top-level report payload accumulated across phases."""

    status: str = "not_started"
    summary: dict[str, Any] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    sections: dict[str, Any] = field(default_factory=dict)
