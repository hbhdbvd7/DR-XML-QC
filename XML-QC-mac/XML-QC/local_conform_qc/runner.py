"""End-to-end local conform QC pipeline."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
import shutil

from .media_scanner import get_import_media_paths, match_xml_clips_to_media, scan_project_media_with_stats
from .models import ReportData, ToolConfig
from .qc_engine import (
    build_import_difference_sections,
    calculate_match_success_percentage,
    collect_problem_issues,
    compare_timeline,
)
from .report_writer import write_reports
from .resolve_api import (
    connect_resolve,
    find_project_ref_media,
    import_project_assets,
    open_or_create_project,
    read_current_timeline_items,
)
from .xml_parser import parse_xml


DEFAULT_RESOLVE_PROJECT_NAME = "LocalConform_QC_Test"


def run_config(config: ToolConfig, workspace_dir: Path) -> list[tuple[Path, Path]]:
    """Run QC for each selected XML path and return report paths."""
    _validate_config(config)
    project_root = Path(config.project_root or ".")
    report_dir = project_root / "QC"
    cache_dir = Path(workspace_dir) / "cache" / "phase8_import_xml"
    cache_dir.mkdir(parents=True, exist_ok=True)

    resolve = connect_resolve()
    project = open_or_create_project(resolve, config.project_name or DEFAULT_RESOLVE_PROJECT_NAME)

    reports: list[tuple[Path, Path]] = []
    for xml_path in _xml_paths(config):
        reports.append(_run_one_xml(config, project, Path(xml_path), report_dir, cache_dir))
    return reports


def _validate_config(config: ToolConfig) -> None:
    if config.project_root is None:
        raise ValueError("Project root is required.")


def _run_one_xml(
    config: ToolConfig,
    project: object,
    xml_path: Path,
    report_dir: Path,
    cache_dir: Path,
) -> tuple[Path, Path]:
    project_root = Path(config.project_root or ".")
    media_root = _media_root(config)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = f"{_safe_report_name(xml_path.stem)}_{timestamp}"
    import_xml_path = cache_dir / f"{report_name}.xml"
    shutil.copyfile(xml_path, import_xml_path)

    scan_result = scan_project_media_with_stats(media_root, reference_paths=config.look_references)
    media_files = scan_result.media_files
    xml_result = parse_xml(xml_path)
    matches = match_xml_clips_to_media(xml_result.clips, media_files)
    import_paths = get_import_media_paths(matches, media_files=media_files, import_all_media=config.import_all_media)
    frame_rate_rows = scan_result.frame_rate_rows
    ref_media_paths = find_project_ref_media(project_root)

    import_result = import_project_assets(
        project=project,
        media_paths=import_paths,
        xml_path=import_xml_path,
        offline_reference_paths=[],
        look_reference_paths=config.look_references,
        project_root=project_root,
        ref_media_paths=ref_media_paths,
        xml_frame_rate=xml_result.sequence_timebase,
        media_folder_name=xml_path.stem,
    )
    timeline_result = read_current_timeline_items(project)
    qc_result = compare_timeline(xml_result, timeline_result)
    sections = build_import_difference_sections(xml_result, matches, import_result, timeline_result, qc_result)
    sections["素材帧率统计"] = frame_rate_rows
    problem_issues = collect_problem_issues(matches, import_result, timeline_result, qc_result)
    match_counts = Counter(match.status for match in matches)

    report = ReportData(
        status=qc_result.status,
        summary={
            "report_name": report_name,
            "测试XML": str(xml_path),
            "导入XML临时副本": str(import_xml_path),
            "项目根目录": str(project_root),
            "镜头素材目录": str(media_root),
            "Resolve项目": project.GetName(),
            "Resolve时间线": import_result.timeline_name or timeline_result.timeline_name,
            "XML帧率": xml_result.sequence_timebase,
            "匹配成功百分比": f"{calculate_match_success_percentage(xml_result, matches, qc_result):.2f}%",
            "XML片段总数": len(xml_result.clips),
            "扫描前媒体文件总数": scan_result.total_candidates,
            "代理素材排除数": scan_result.proxy_excluded,
            "扫描素材文件总数": len(media_files),
            "匹配统计": dict(match_counts),
            "请求导入素材数": len(import_paths),
            "Resolve实际导入素材数": len(import_result.imported_media),
            "Resolve导入ref数": len(import_result.imported_ref_media),
            "Resolve时间线片段数": len(timeline_result.video_items),
            "Resolve离线片段数": sum(1 for item in timeline_result.video_items if item.is_offline),
            "QC状态": qc_result.status,
            "问题数量": len(problem_issues),
        },
        issues=problem_issues,
        sections=sections,
    )
    return write_reports(report, report_dir)


def _xml_paths(config: ToolConfig) -> list[Path]:
    if config.xml_paths:
        xml_paths = [Path(path).expanduser() for path in config.xml_paths]
        missing = [path for path in xml_paths if not path.is_file()]
        if missing:
            raise ValueError("Selected XML file was not found: " + "; ".join(str(path) for path in missing))
        return xml_paths
    project_root = Path(config.project_root or ".")
    edit_dir = project_root / "edit"
    if not edit_dir.is_dir():
        raise ValueError(f"XML paths were not selected and edit folder was not found: {edit_dir}")
    xml_paths = sorted(edit_dir.rglob("*.xml"), key=lambda path: str(path).casefold())
    if not xml_paths:
        raise ValueError(f"No XML files were found under edit folder: {edit_dir}")
    return xml_paths


def _media_root(config: ToolConfig) -> Path:
    if config.media_root is not None:
        return Path(config.media_root)
    project_root = Path(config.project_root or ".")
    footage_dir = project_root / "footage"
    if not footage_dir.is_dir():
        raise ValueError(f"Shot media path was not selected and footage folder was not found: {footage_dir}")
    return footage_dir


def _safe_report_name(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in value).strip("_")
    return safe or "local_conform_qc"
