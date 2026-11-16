# -*- coding: utf-8 -*-
"""模拟学情数据索引.xlsx 结构探查（只读，不修改原文件）。"""
import sys

import openpyxl

sys.stdout.reconfigure(encoding="utf-8")
P = r"D:\学习资料\AI竞赛\工作区\赛题材料\赛题数据\赛题资料包\4_赛题数据\模拟学情数据索引.xlsx"
wb = openpyxl.load_workbook(P, data_only=True)
print("工作表:", wb.sheetnames)
for ws in wb.worksheets:
    print(f"\n=== {ws.title}  dims={ws.dimensions}  rows={ws.max_row} cols={ws.max_column}")
    for r in ws.iter_rows(min_row=1, max_row=min(6, ws.max_row), values_only=True):
        cells = ["" if v is None else str(v).replace("\n", "\\n")[:48] for v in r]
        print("  | " + " | ".join(cells))
