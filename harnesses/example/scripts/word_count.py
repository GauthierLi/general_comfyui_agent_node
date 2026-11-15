"""统计 UTF-8 文本文件的字符数和行数。"""
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
print(f"chars={len(text)} lines={len(text.splitlines())}")
