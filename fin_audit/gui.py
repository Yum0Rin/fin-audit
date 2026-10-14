"""GUI 外壳（薄壳）。

只是把核心引擎包一层 tkinter 界面：选配置 → 运行 → 看汇总 → 打开报告。
所有稽核逻辑都在 :mod:`fin_audit.engine`，本模块不做任何规则计算。

运行::

    python -m fin_audit.gui
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser
from pathlib import Path

from .engine import AuditEngine, load_config
from .report import write_csv, write_html


class AuditApp(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=12)
        self.master = master
        self.pack(fill="both", expand=True)
        self.html_path = None
        self._build()

    def _build(self):
        self.master.title("fin-audit · 金融数据稽核工具")
        self.master.geometry("760x560")

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="规则配置 (JSON):").pack(side="left")
        self.config_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.config_var).pack(
            side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="浏览…", command=self._pick).pack(side="left")

        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=8)
        ttk.Button(btns, text="运行稽核", command=self._run).pack(side="left")
        ttk.Button(btns, text="打开 HTML 报告", command=self._open).pack(side="left", padx=6)

        self.text = tk.Text(self, wrap="none", font=("Consolas", 10))
        self.text.pack(fill="both", expand=True)

    def _pick(self):
        path = filedialog.askopenfilename(
            title="选择规则配置", filetypes=[("JSON", "*.json"), ("所有文件", "*.*")])
        if path:
            self.config_var.set(path)

    def _run(self):
        config_path = self.config_var.get().strip()
        if not config_path:
            messagebox.showwarning("提示", "请先选择规则配置文件")
            return
        try:
            config = load_config(config_path)
            result = AuditEngine(config).run()
            if config.html_report:
                self.html_path = write_html(result, config.resolve(config.html_report))
            if config.csv_report:
                write_csv(result, config.resolve(config.csv_report))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("运行失败", str(exc))
            return

        self.text.delete("1.0", "end")
        self.text.insert("end", f"源数据  : {result.source_path} ({result.source_rows} 行)\n")
        self.text.insert("end", f"目标数据: {result.target_path} ({result.target_rows} 行)\n")
        self.text.insert("end", "-" * 60 + "\n")
        for r in result.rule_results:
            self.text.insert("end", f"[{'通过' if r.passed else '失败'}] "
                                    f"{r.name}  差异 {r.diff_count} 条  ({r.message})\n")
        self.text.insert("end", "-" * 60 + "\n")
        self.text.insert("end", f"结论：{'' if result.passed else '存在差异，'}"
                                f"差异合计 {result.total_diff} 条\n")
        if self.html_path:
            self.text.insert("end", f"HTML 报告：{self.html_path}\n")

    def _open(self):
        if not self.html_path:
            messagebox.showinfo("提示", "请先运行一次稽核")
            return
        webbrowser.open(Path(self.html_path).resolve().as_uri())


def main():
    root = tk.Tk()
    AuditApp(root)
    root.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
