"""XML-QC GUI tool for DaVinci Resolve Workspace > Scripts.

This script is intentionally self-contained inside the XML-QC folder. It uses
the bundled local_conform_qc package copied next to this file.
"""

from __future__ import annotations

from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import traceback


def _initial_script_dir() -> Path | None:
    file_name = globals().get("__file__")
    if file_name:
        return Path(file_name).resolve().parent

    code_file = getattr(_initial_script_dir, "__code__", None)
    code_path = getattr(code_file, "co_filename", None)
    if code_path and not str(code_path).startswith("<"):
        return Path(code_path).resolve().parent

    return None


_THIS_DIR = _initial_script_dir()
if _THIS_DIR is not None:
    _THIS_DIR_TEXT = str(_THIS_DIR)
    if _THIS_DIR_TEXT not in sys.path:
        sys.path.insert(0, _THIS_DIR_TEXT)

import local_conform_qc
from local_conform_qc.models import ToolConfig
from local_conform_qc.runner import run_config


def _script_dir() -> Path:
    file_name = globals().get("__file__")
    if file_name:
        return Path(file_name).resolve().parent

    initial_dir = _initial_script_dir()
    if initial_dir is not None:
        return initial_dir

    package_file = getattr(local_conform_qc, "__file__", None)
    if package_file:
        return Path(package_file).resolve().parent.parent

    if sys.argv and sys.argv[0]:
        argv_path = Path(sys.argv[0]).expanduser()
        try:
            resolved = argv_path.resolve()
        except OSError:
            resolved = argv_path
        if resolved.exists():
            return resolved.parent if resolved.is_file() else resolved

    return Path.cwd()


class XmlQcApp(tk.Tk):
    """Small operator-facing GUI for XML conform QC."""

    def __init__(self) -> None:
        super().__init__()
        self.title("XML-QC")
        self.geometry("780x560")
        self.minsize(680, 500)
        self.xml_paths: list[Path] = []
        self.log_queue: queue.Queue[str] = queue.Queue()
        self._build_ui()
        self.after(100, self._drain_log_queue)

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=14)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(5, weight=1)

        self.project_root_var = tk.StringVar()
        self.media_root_var = tk.StringVar()
        self.project_name_var = tk.StringVar(value="LocalConform_QC_Test")
        self.import_all_var = tk.BooleanVar(value=False)

        ttk.Label(container, text="项目根目录").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(container, textvariable=self.project_root_var).grid(row=0, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(container, text="选择", command=self._pick_project_root).grid(row=0, column=2, pady=4)

        ttk.Label(container, text="XML文件").grid(row=1, column=0, sticky="nw", pady=4)
        xml_frame = ttk.Frame(container)
        xml_frame.grid(row=1, column=1, sticky="ew", padx=8, pady=4)
        xml_frame.columnconfigure(0, weight=1)
        self.xml_label_var = tk.StringVar(value="未选择时自动使用 项目根目录/edit 下的 XML")
        ttk.Label(xml_frame, textvariable=self.xml_label_var, wraplength=460).grid(row=0, column=0, sticky="ew")
        xml_buttons = ttk.Frame(container)
        xml_buttons.grid(row=1, column=2, sticky="n", pady=4)
        ttk.Button(xml_buttons, text="添加", command=self._pick_xml_files).pack(fill=tk.X)
        ttk.Button(xml_buttons, text="清空", command=self._clear_xml_files).pack(fill=tk.X, pady=(6, 0))

        ttk.Label(container, text="镜头路径").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(container, textvariable=self.media_root_var).grid(row=2, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(container, text="选择", command=self._pick_media_root).grid(row=2, column=2, pady=4)

        hint = "未选择镜头路径时自动使用 项目根目录/footage；ref 文件夹会自动导入 ref 媒体池。"
        ttk.Label(container, text=hint, foreground="#555").grid(row=3, column=1, sticky="w", padx=8, pady=(0, 8))

        ttk.Label(container, text="Resolve项目").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(container, textvariable=self.project_name_var).grid(row=4, column=1, sticky="ew", padx=8, pady=4)
        ttk.Checkbutton(container, text="导入全部扫描素材", variable=self.import_all_var).grid(
            row=4, column=2, sticky="w", pady=4
        )

        self.log_text = tk.Text(container, height=14, wrap=tk.WORD)
        self.log_text.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(12, 8))
        self.log_text.configure(state=tk.DISABLED)

        actions = ttk.Frame(container)
        actions.grid(row=6, column=0, columnspan=3, sticky="ew")
        actions.columnconfigure(0, weight=1)
        self.run_button = ttk.Button(actions, text="开始 XML-QC", command=self._start_run)
        self.run_button.grid(row=0, column=1, sticky="e")

    def _pick_project_root(self) -> None:
        value = filedialog.askdirectory(title="选择项目根目录")
        if value:
            self.project_root_var.set(value)

    def _pick_xml_files(self) -> None:
        values = filedialog.askopenfilenames(
            title="选择 XML 文件",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
        )
        if values:
            self.xml_paths.extend(Path(value) for value in values)
            unique = []
            seen = set()
            for path in self.xml_paths:
                key = str(path).casefold()
                if key in seen:
                    continue
                seen.add(key)
                unique.append(path)
            self.xml_paths = unique
            self._update_xml_label()

    def _clear_xml_files(self) -> None:
        self.xml_paths.clear()
        self._update_xml_label()

    def _update_xml_label(self) -> None:
        if not self.xml_paths:
            self.xml_label_var.set("未选择时自动使用 项目根目录/edit 下的 XML")
            return
        self.xml_label_var.set("; ".join(path.name for path in self.xml_paths))

    def _pick_media_root(self) -> None:
        value = filedialog.askdirectory(title="选择镜头素材路径")
        if value:
            self.media_root_var.set(value)

    def _start_run(self) -> None:
        project_root_text = self.project_root_var.get().strip()
        if not project_root_text:
            messagebox.showerror("XML-QC", "请选择项目根目录。")
            return
        config = ToolConfig(
            project_root=Path(project_root_text),
            xml_paths=list(self.xml_paths),
            media_root=Path(self.media_root_var.get().strip()) if self.media_root_var.get().strip() else None,
            project_name=self.project_name_var.get().strip() or None,
            import_all_media=self.import_all_var.get(),
        )
        self.run_button.configure(state=tk.DISABLED)
        self._log("开始运行 XML-QC...")
        thread = threading.Thread(target=self._run_worker, args=(config,), daemon=True)
        thread.start()

    def _run_worker(self, config: ToolConfig) -> None:
        try:
            reports = run_config(config, _script_dir())
        except Exception:
            self.log_queue.put(traceback.format_exc())
            self.log_queue.put("__DONE_ERROR__")
            return
        for json_path, html_path in reports:
            self.log_queue.put(f"报告已生成: {json_path}")
            self.log_queue.put(f"HTML: {html_path}")
        self.log_queue.put("__DONE_OK__")

    def _drain_log_queue(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if message == "__DONE_OK__":
                self._log("XML-QC 完成。")
                self.run_button.configure(state=tk.NORMAL)
                messagebox.showinfo("XML-QC", "流程已完成，报告已生成。")
            elif message == "__DONE_ERROR__":
                self._log("XML-QC 失败。")
                self.run_button.configure(state=tk.NORMAL)
                messagebox.showerror("XML-QC", "运行失败，详情见日志。")
            else:
                self._log(message)
        self.after(100, self._drain_log_queue)

    def _log(self, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message.rstrip() + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)


def main() -> int:
    app = XmlQcApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
