"""Tkinter workspace for M4A Transcriber TW."""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Dict, List

from dotenv import load_dotenv, set_key

from transcriber.config import (
    APP_VERSION,
    AudioConfig,
    DEFAULT_TRANSCRIPTION_MODEL,
    DEFAULT_TRANSLATION_MODEL,
    ProcessingConfig,
    SUPPORTED_AUDIO_EXTENSIONS,
    SUPPORTED_TRANSCRIPTION_MODELS,
    SUPPORTED_TRANSLATION_MODELS,
)
from transcriber.pipeline import ProcessingCancelled, TranscriptionPipeline


LOGGER = logging.getLogger("m4a_transcriber.gui")


class TranscriptionApp:
    COLORS = {
        "background": "#f4f6f8",
        "surface": "#ffffff",
        "sidebar": "#17212b",
        "sidebar_text": "#edf2f7",
        "accent": "#2563eb",
        "muted": "#64748b",
        "border": "#dbe2ea",
        "success": "#0f766e",
        "danger": "#b42318",
    }

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.input_files: List[Path] = []
        self.result_paths: List[Path] = []
        self.events: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self._configure_window()
        self._configure_style()
        self._build_ui()
        self._load_api_key()
        self._install_logging()
        self.reload_results()
        self.root.after(100, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _configure_window(self) -> None:
        self.root.title(f"M4A Transcriber TW {APP_VERSION}")
        self.root.geometry("1180x800")
        self.root.minsize(980, 680)
        self.root.configure(bg=self.COLORS["background"])

    def _configure_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=self.COLORS["background"])
        style.configure("Surface.TFrame", background=self.COLORS["surface"])
        style.configure("Sidebar.TFrame", background=self.COLORS["sidebar"])
        style.configure("Sidebar.TLabel", background=self.COLORS["sidebar"], foreground=self.COLORS["sidebar_text"])
        style.configure("Title.TLabel", background=self.COLORS["surface"], foreground="#0f172a", font=("TkDefaultFont", 18, "bold"))
        style.configure("Section.TLabel", background=self.COLORS["surface"], foreground="#0f172a", font=("TkDefaultFont", 11, "bold"))
        style.configure("Muted.TLabel", background=self.COLORS["surface"], foreground=self.COLORS["muted"])
        style.configure("Accent.TButton", background=self.COLORS["accent"], foreground="white", padding=(16, 9))
        style.map("Accent.TButton", background=[("active", "#1d4ed8"), ("disabled", "#94a3b8")])
        style.configure("TButton", padding=(10, 7))
        style.configure("TLabelframe", background=self.COLORS["surface"], bordercolor=self.COLORS["border"])
        style.configure("TLabelframe.Label", background=self.COLORS["surface"], foreground="#334155", font=("TkDefaultFont", 10, "bold"))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True)
        self._build_sidebar(outer)

        workspace = ttk.Frame(outer, style="Surface.TFrame", padding=20)
        workspace.pack(side="left", fill="both", expand=True)
        self._build_header(workspace)
        body = ttk.Panedwindow(workspace, orient="vertical")
        body.pack(fill="both", expand=True, pady=(16, 12))

        settings = ttk.Frame(body, style="Surface.TFrame")
        results = ttk.Frame(body, style="Surface.TFrame")
        body.add(settings, weight=3)
        body.add(results, weight=2)
        self._build_settings(settings)
        self._build_results(results)
        self._build_footer(workspace)

    def _build_sidebar(self, parent) -> None:
        sidebar = ttk.Frame(parent, style="Sidebar.TFrame", width=330, padding=20)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        ttk.Label(sidebar, text="工作佇列", style="Sidebar.TLabel", font=("TkDefaultFont", 16, "bold")).pack(anchor="w")
        ttk.Label(sidebar, text="加入音檔後即可開始批次處理", style="Sidebar.TLabel").pack(anchor="w", pady=(4, 14))

        self.file_list = tk.Listbox(
            sidebar,
            selectmode="extended",
            relief="flat",
            bg="#22303d",
            fg=self.COLORS["sidebar_text"],
            selectbackground=self.COLORS["accent"],
            selectforeground="white",
            highlightthickness=0,
            activestyle="none",
            font=("TkDefaultFont", 10),
        )
        self.file_list.pack(fill="both", expand=True, pady=(0, 12))

        row = ttk.Frame(sidebar, style="Sidebar.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="加入檔案", command=self.add_files).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(row, text="加入資料夾", command=self.add_folder).pack(side="left", expand=True, fill="x", padx=(4, 0))
        row2 = ttk.Frame(sidebar, style="Sidebar.TFrame")
        row2.pack(fill="x", pady=(8, 0))
        ttk.Button(row2, text="移除選取", command=self.remove_selected).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(row2, text="清除", command=self.clear_files).pack(side="left", expand=True, fill="x", padx=(4, 0))

    def _build_header(self, parent) -> None:
        header = ttk.Frame(parent, style="Surface.TFrame")
        header.pack(fill="x")
        title_block = ttk.Frame(header, style="Surface.TFrame")
        title_block.pack(side="left")
        ttk.Label(title_block, text="音檔轉錄工作台", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_block,
            text="gpt-transcribe 轉錄，GPT-5.6 Luna 忠實翻譯，reasoning effort: none",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(3, 0))
        ttk.Button(header, text="關於", command=self.show_about).pack(side="right")

    def _build_settings(self, parent) -> None:
        columns = ttk.Frame(parent, style="Surface.TFrame")
        columns.pack(fill="both", expand=True)
        left = ttk.Frame(columns, style="Surface.TFrame")
        right = ttk.Frame(columns, style="Surface.TFrame")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        api = ttk.LabelFrame(left, text="連線與輸出", padding=12)
        api.pack(fill="x")
        self.api_key = tk.StringVar()
        self.api_entry = ttk.Entry(api, textvariable=self.api_key, show="*", width=38)
        self.api_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(api, text="顯示", variable=self.show_key, command=self._toggle_key).grid(row=0, column=1)
        ttk.Button(api, text="儲存", command=self.save_api_key).grid(row=0, column=2, padx=(6, 0))
        self.output_dir = tk.StringVar(value="./text")
        ttk.Entry(api, textvariable=self.output_dir).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0), padx=(0, 6))
        ttk.Button(api, text="選擇輸出", command=self.select_output).grid(row=1, column=2, pady=(10, 0))
        api.columnconfigure(0, weight=1)

        models = ttk.LabelFrame(left, text="模型與效能", padding=12)
        models.pack(fill="x", pady=(12, 0))
        self.transcription_model = tk.StringVar(value=DEFAULT_TRANSCRIPTION_MODEL)
        self.translation_model = tk.StringVar(value=DEFAULT_TRANSLATION_MODEL)
        self.languages = tk.StringVar()
        self.max_size = tk.IntVar(value=20)
        self.max_duration = tk.IntVar(value=10)
        self.asr_workers = tk.IntVar(value=3)
        self.translation_workers = tk.IntVar(value=2)
        fields = [
            ("轉錄模型", ttk.Combobox(models, textvariable=self.transcription_model, values=SUPPORTED_TRANSCRIPTION_MODELS, state="readonly")),
            ("翻譯模型", ttk.Combobox(models, textvariable=self.translation_model, values=SUPPORTED_TRANSLATION_MODELS, state="readonly")),
            ("語言提示", ttk.Entry(models, textvariable=self.languages)),
        ]
        for row, (label, widget) in enumerate(fields):
            ttk.Label(models, text=label).grid(row=row, column=0, sticky="w", pady=3)
            widget.grid(row=row, column=1, columnspan=3, sticky="ew", padx=(10, 0), pady=3)
        numeric = [
            ("大小 MB", self.max_size, 5, 24),
            ("片段分鐘", self.max_duration, 1, 30),
            ("轉錄並行", self.asr_workers, 1, 8),
            ("翻譯並行", self.translation_workers, 1, 8),
        ]
        for index, (label, variable, minimum, maximum) in enumerate(numeric):
            row = 3 + index // 2
            column = (index % 2) * 2
            ttk.Label(models, text=label).grid(row=row, column=column, sticky="w", pady=3)
            ttk.Spinbox(models, from_=minimum, to=maximum, textvariable=variable, width=7).grid(
                row=row, column=column + 1, sticky="w", padx=(8, 14), pady=3
            )
        models.columnconfigure(1, weight=1)
        models.columnconfigure(3, weight=1)

        context_frame = ttk.LabelFrame(right, text="錄音背景與術語", padding=12)
        context_frame.pack(fill="both", expand=True)
        ttk.Label(context_frame, text="錄音背景", style="Muted.TLabel").pack(anchor="w")
        self.context_text = tk.Text(context_frame, height=4, wrap="word", relief="solid", borderwidth=1)
        self.context_text.pack(fill="x", pady=(4, 10))
        ttk.Label(context_frame, text="正確術語，每行一個", style="Muted.TLabel").pack(anchor="w")
        self.keywords_text = tk.Text(context_frame, height=5, wrap="word", relief="solid", borderwidth=1)
        self.keywords_text.pack(fill="both", expand=True, pady=(4, 10))
        ttk.Label(context_frame, text="格式偏好", style="Muted.TLabel").pack(anchor="w")
        self.style_text = tk.Text(context_frame, height=3, wrap="word", relief="solid", borderwidth=1)
        self.style_text.pack(fill="x", pady=(4, 4))
        ttk.Label(
            context_frame,
            text="忠實翻譯、禁止摘要與逐段完整輸出的核心規則受保護，以上內容無法覆寫核心規則。",
            style="Muted.TLabel",
            wraplength=480,
        ).pack(anchor="w")

    def _build_results(self, parent) -> None:
        header = ttk.Frame(parent, style="Surface.TFrame")
        header.pack(fill="x", pady=(12, 6))
        ttk.Label(header, text="結果與活動", style="Section.TLabel").pack(side="left")
        ttk.Button(header, text="重新整理", command=self.reload_results).pack(side="right")

        pane = ttk.Panedwindow(parent, orient="horizontal")
        pane.pack(fill="both", expand=True)
        result_frame = ttk.Frame(pane, style="Surface.TFrame")
        log_frame = ttk.Frame(pane, style="Surface.TFrame")
        pane.add(result_frame, weight=3)
        pane.add(log_frame, weight=2)

        result_bar = ttk.Frame(result_frame, style="Surface.TFrame")
        result_bar.pack(fill="x")
        self.result_selector = ttk.Combobox(result_bar, state="readonly")
        self.result_selector.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.result_selector.bind("<<ComboboxSelected>>", self.load_selected_result)
        ttk.Button(result_bar, text="開啟資料夾", command=self.open_result_folder).pack(side="right")
        self.result_text = scrolledtext.ScrolledText(result_frame, height=10, wrap="word", relief="solid", borderwidth=1)
        self.result_text.pack(fill="both", expand=True, pady=(6, 0), padx=(0, 8))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, wrap="word", state="disabled", relief="solid", borderwidth=1)
        self.log_text.pack(fill="both", expand=True, padx=(8, 0))

    def _build_footer(self, parent) -> None:
        footer = ttk.Frame(parent, style="Surface.TFrame")
        footer.pack(fill="x")
        self.progress = tk.DoubleVar(value=0)
        ttk.Progressbar(footer, variable=self.progress, maximum=100).pack(side="left", fill="x", expand=True)
        self.status = tk.StringVar(value="就緒")
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel", width=28, anchor="center").pack(side="left", padx=12)
        self.stop_button = ttk.Button(footer, text="停止", command=self.stop, state="disabled")
        self.stop_button.pack(side="right")
        self.start_button = ttk.Button(footer, text="開始處理", style="Accent.TButton", command=self.start)
        self.start_button.pack(side="right", padx=(0, 8))

    def _install_logging(self) -> None:
        handler = QueueLogHandler(self.events)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def _load_api_key(self) -> None:
        load_dotenv(".env", override=True)
        self.api_key.set(os.getenv("OPENAI_API_KEY", ""))

    def _toggle_key(self) -> None:
        self.api_entry.configure(show="" if self.show_key.get() else "*")

    def save_api_key(self) -> None:
        key = self.api_key.get().strip()
        if not key:
            messagebox.showerror("API Key", "請先輸入 API Key")
            return
        set_key(".env", "OPENAI_API_KEY", key)
        os.environ["OPENAI_API_KEY"] = key
        self.status.set("API Key 已儲存於本機")

    def add_files(self) -> None:
        values = filedialog.askopenfilenames(
            title="選擇音檔",
            filetypes=[("音檔", "*.m4a *.mp3 *.wav *.flac *.aac *.mp4 *.mpeg *.webm"), ("所有檔案", "*.*")],
        )
        self._append_inputs(Path(value) for value in values)

    def add_folder(self) -> None:
        value = filedialog.askdirectory(title="選擇音檔資料夾")
        if value:
            self._append_inputs(
                path for path in sorted(Path(value).rglob("*"))
                if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
            )

    def _append_inputs(self, paths) -> None:
        known = {path.resolve() for path in self.input_files}
        for path in paths:
            resolved = path.resolve()
            if resolved not in known and resolved.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                self.input_files.append(resolved)
                self.file_list.insert(tk.END, resolved.name)
                known.add(resolved)
        self.status.set(f"佇列中有 {len(self.input_files)} 個檔案")

    def remove_selected(self) -> None:
        for index in reversed(self.file_list.curselection()):
            self.file_list.delete(index)
            del self.input_files[index]
        self.status.set(f"佇列中有 {len(self.input_files)} 個檔案")

    def clear_files(self) -> None:
        self.input_files.clear()
        self.file_list.delete(0, tk.END)
        self.status.set("工作佇列已清除")

    def select_output(self) -> None:
        value = filedialog.askdirectory(title="選擇結果根目錄")
        if value:
            self.output_dir.set(value)
            self.reload_results()

    def _snapshot(self) -> Dict:
        languages = tuple(part.strip() for part in self.languages.get().replace("，", ",").split(",") if part.strip())
        keywords = tuple(
            line.strip() for line in self.keywords_text.get("1.0", tk.END).splitlines() if line.strip()
        )
        config = ProcessingConfig(
            transcription_model=self.transcription_model.get(),
            translation_model=self.translation_model.get(),
            languages=languages,
            keywords=keywords,
            recording_context=self.context_text.get("1.0", tk.END).strip(),
            style_preference=self.style_text.get("1.0", tk.END).strip(),
            asr_workers=self.asr_workers.get(),
            translation_workers=self.translation_workers.get(),
            audio=AudioConfig(
                max_size_mb=self.max_size.get(),
                max_duration_min=self.max_duration.get(),
            ),
        )
        config.validate()
        return {
            "api_key": self.api_key.get().strip(),
            "inputs": tuple(self.input_files),
            "output": Path(self.output_dir.get()).expanduser(),
            "config": config,
        }

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            snapshot = self._snapshot()
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("設定錯誤", str(exc))
            return
        if not snapshot["api_key"]:
            messagebox.showerror("設定錯誤", "請先輸入 OpenAI API Key")
            return
        if not snapshot["inputs"]:
            messagebox.showerror("設定錯誤", "請至少加入一個音檔")
            return
        snapshot["output"].mkdir(parents=True, exist_ok=True)
        self.stop_event.clear()
        self.progress.set(0)
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set("正在初始化")
        self.worker = threading.Thread(target=self._run, args=(snapshot,), daemon=True)
        self.worker.start()

    def _run(self, snapshot: Dict) -> None:
        successes = []
        failures = []
        try:
            pipeline = TranscriptionPipeline(api_key=snapshot["api_key"])
            total = len(snapshot["inputs"])
            for index, source in enumerate(snapshot["inputs"], 1):
                if self.stop_event.is_set():
                    break
                self.events.put(("file_start", {"name": source.name, "index": index, "total": total}))
                try:
                    result = pipeline.process(
                        source,
                        snapshot["output"],
                        snapshot["config"],
                        progress=lambda event, file_index=index: self.events.put(
                            ("progress", {**event, "file_index": file_index, "file_total": total})
                        ),
                        should_stop=self.stop_event.is_set,
                    )
                    successes.append(result)
                    self.events.put(("file_done", {"result": result, "index": index, "total": total}))
                except ProcessingCancelled:
                    break
                except Exception as exc:
                    failures.append((source, exc))
                    self.events.put(("file_failed", {"name": source.name, "error": str(exc)}))
        except Exception as exc:
            self.events.put(("fatal", str(exc)))
        finally:
            self.events.put(("batch_done", {"successes": successes, "failures": failures, "stopped": self.stop_event.is_set()}))

    def stop(self) -> None:
        self.stop_event.set()
        self.stop_button.configure(state="disabled")
        self.status.set("正在停止，等待目前 API 呼叫完成")

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "file_start":
                    self.status.set(f"處理 {payload['index']}/{payload['total']}: {payload['name']}")
                elif kind == "progress":
                    base = (payload["file_index"] - 1) / payload["file_total"] * 100
                    completed = payload.get("completed", 0)
                    total = payload.get("total", 1) or 1
                    self.progress.set(base + (completed / total) * (100 / payload["file_total"]))
                elif kind == "file_done":
                    self.progress.set(payload["index"] / payload["total"] * 100)
                elif kind == "file_failed":
                    self.status.set(f"失敗: {payload['name']}")
                elif kind == "fatal":
                    messagebox.showerror("處理失敗", payload)
                elif kind == "batch_done":
                    self._batch_done(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _batch_done(self, payload: Dict) -> None:
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.reload_results()
        successes = len(payload["successes"])
        failures = len(payload["failures"])
        if payload["stopped"]:
            self.status.set(f"已停止；完成 {successes}，失敗 {failures}")
        elif failures:
            self.status.set(f"完成 {successes}，失敗 {failures}")
            messagebox.showwarning("批次完成", f"成功 {successes} 個檔案，失敗 {failures} 個檔案。請查看活動記錄。")
        else:
            self.progress.set(100)
            self.status.set(f"全部完成，共 {successes} 個檔案")

    def reload_results(self) -> None:
        root = Path(self.output_dir.get()).expanduser()
        self.result_paths = sorted(root.glob("*/final.txt"), key=lambda path: path.stat().st_mtime, reverse=True) if root.exists() else []
        self.result_selector["values"] = [path.parent.name for path in self.result_paths]
        if self.result_paths:
            self.result_selector.current(0)
            self.load_selected_result()
        else:
            self.result_selector.set("")
            self.result_text.delete("1.0", tk.END)

    def load_selected_result(self, event=None) -> None:
        index = self.result_selector.current()
        if index < 0 or index >= len(self.result_paths):
            return
        try:
            content = self.result_paths[index].read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("讀取失敗", str(exc))
            return
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert("1.0", content)

    def open_result_folder(self) -> None:
        index = self.result_selector.current()
        if index < 0 or index >= len(self.result_paths):
            return
        path = self.result_paths[index].parent
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror("開啟失敗", str(exc))

    def show_about(self) -> None:
        messagebox.showinfo(
            "關於",
            f"M4A Transcriber TW\n版本 {APP_VERSION}\n\n"
            "預設轉錄模型: gpt-transcribe\n"
            "預設翻譯模型: gpt-5.6-luna\n"
            "推理強度: none\n\n"
            "結果依音檔分類，支援中斷續跑與原始轉錄保留。",
        )

    def _close(self) -> None:
        self.stop_event.set()
        self.root.destroy()


class QueueLogHandler(logging.Handler):
    def __init__(self, events: queue.Queue) -> None:
        super().__init__()
        self.events = events

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.events.put(("log", self.format(record)))
        except Exception:
            self.handleError(record)


def main() -> None:
    root = tk.Tk()
    TranscriptionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
