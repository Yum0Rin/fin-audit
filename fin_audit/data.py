"""数据加载与类型推断。

审计的输入是两张表（源数据 / 目标报送数据）。数据层优先使用 pandas：读入后对
「整列都能解析为数字」的列做数值化，方便后续金额勾稽与数值比较；主键、币种、状态
等文本列保持字符串。
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import pandas as pd


def _coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """把整列都可以解析成数字的列转成 float，空串转成 NaN。"""
    out = df.copy()
    for col in out.columns:
        series = out[col]
        non_empty = series[series.astype(str).str.strip() != ""]
        if len(non_empty) == 0:
            continue
        numeric = pd.to_numeric(non_empty, errors="coerce")
        if numeric.notna().all():
            cleaned = series.astype(str).str.strip().replace("", None)
            out[col] = pd.to_numeric(cleaned, errors="coerce")
    return out


def load_table(path: Union[str, Path]) -> pd.DataFrame:
    """读取一张 CSV 表（全部按字符串读入，再做数值推断）。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]
    return _coerce_numeric(df)


def load_frames(source: Union[str, Path], target: Union[str, Path]):
    """一次性读取源表与目标表。"""
    return load_table(source), load_table(target)
