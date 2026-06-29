"""JSON and HTML report writing utilities."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from html import escape
import json
from pathlib import Path
import re
from typing import Any

from .models import Issue, ReportData


def write_reports(report: ReportData, output_dir: Path) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    payload = _to_plain(report)
    if isinstance(payload, dict) and isinstance(payload.get("sections"), dict):
        payload["sections"] = dict(_ordered_sections(payload["sections"]))
        if payload["sections"]:
            payload.pop("issues", None)
    report_name = _report_file_stem(report)
    json_path = destination / f"{report_name}.json"
    html_path = destination / f"{report_name}.html"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(_render_html(payload), encoding="utf-8")
    return json_path, html_path


def build_failure_report(message: str, context: dict[str, Any] | None = None) -> ReportData:
    return ReportData(
        status="error",
        summary={"message": message},
        issues=[Issue(code="pipeline_failed", severity="ERROR", message=message, context=context or {})],
    )


def _report_file_stem(report: ReportData) -> str:
    name = str(report.summary.get("report_name") or "")
    if not name:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"local_conform_qc_{timestamp}_{report.status}"
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
    return safe_name or "local_conform_qc_report"


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _to_plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_plain(item) for item in value]
    return value


def _render_html(payload: dict[str, Any]) -> str:
    status = str(payload.get("status", "unknown"))
    summary = payload.get("summary", {})
    sections = payload.get("sections", {})
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>本地套底 QC 报告</title>",
        "<style>",
        _css(),
        "</style>",
        "</head>",
        "<body>",
        "<main>",
        "<h1>本地套底 QC 报告</h1>",
        f'<p class="status status-{escape(status.lower())}">状态：{escape(_status_label(status))}</p>',
        _render_key_value_section("摘要", summary),
        _render_sections(sections),
        "</main>",
        "</body>",
        "</html>",
    ])


def _render_key_value_section(title: str, values: Any) -> str:
    if not isinstance(values, dict):
        return f"<section><h2>{escape(title)}</h2><pre>{escape(json.dumps(values, ensure_ascii=False, indent=2))}</pre></section>"
    rows = "\n".join(f"<tr><th>{escape(str(key))}</th><td>{escape(_short_text(value))}</td></tr>" for key, value in values.items())
    return f"<section><h2>{escape(title)}</h2><table>{rows}</table></section>"


def _render_sections(sections: Any) -> str:
    if not isinstance(sections, dict) or not sections:
        return ""
    rendered = []
    for name, value in _ordered_sections(sections):
        if isinstance(value, dict):
            rendered.append(_render_key_value_section(str(name), value))
        elif _is_list_of_dicts(value):
            rendered.append(_render_dict_list_section(str(name), value))
        else:
            rendered.append(f"<section><h2>{escape(str(name))}</h2><pre>{escape(json.dumps(value, ensure_ascii=False, indent=2))}</pre></section>")
    return "\n".join(rendered)


def _ordered_sections(sections: dict[str, Any]) -> list[tuple[str, Any]]:
    priority = ["镜头缺失报告", "镜头名不匹配报告", "多个素材候选报告", "素材帧率统计", "导入失败尝试", "轨道和数量差异", "时间线离线片段", "其他问题", "出入点时间码问题"]
    ranked: list[tuple[str, Any]] = []
    used: set[str] = set()
    for name in priority:
        if name in sections:
            ranked.append((name, sections[name]))
            used.add(name)
    ranked.extend((name, value) for name, value in sections.items() if name not in used)
    return ranked


def _render_dict_list_section(title: str, values: list[dict[str, Any]]) -> str:
    if not values:
        return f"<section><h2>{escape(title)}</h2><p>没有问题。</p></section>"
    columns: list[str] = []
    for row in values:
        for key in row:
            if key not in columns:
                columns.append(key)
    header = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body_rows = []
    for row in values:
        cells = "".join(f"<td>{escape(_short_text(row.get(column)))}</td>" for column in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    return f"<section><h2>{escape(title)}</h2><table><thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></section>"


def _is_list_of_dicts(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def _status_label(status: str) -> str:
    return {"pass": "通过", "fail": "未通过", "error": "错误"}.get(status.lower(), status)


def _short_text(value: Any, limit: int = 500) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return text if len(text) <= limit else f"{text[:limit]}..."


def _css() -> str:
    return """
body { margin: 0; font-family: Arial, sans-serif; color: #202124; background: #f6f7f9; }
main { max-width: 1180px; margin: 0 auto; padding: 32px 24px; }
h1 { margin: 0 0 12px; font-size: 28px; }
h2 { margin: 28px 0 12px; font-size: 18px; }
.status { display: inline-block; padding: 6px 10px; border-radius: 4px; font-weight: 700; background: #e8eaed; }
.status-pass { background: #dff5e3; color: #166329; }
.status-fail, .status-error { background: #fde7e9; color: #9b1c31; }
table { width: 100%; border-collapse: collapse; background: #fff; }
th, td { border: 1px solid #d9dce1; padding: 8px 10px; text-align: left; vertical-align: top; }
th { width: 220px; background: #eef1f5; }
pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: Consolas, monospace; font-size: 12px; }
section { margin-bottom: 22px; }
"""
