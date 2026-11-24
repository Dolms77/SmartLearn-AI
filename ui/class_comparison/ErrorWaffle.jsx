import React, { useState } from "react";
import "./styles.css";

export const mockErrors = [
  { id: "C1", label: "概念误解", count: 80 },
  { id: "C2", label: "计算失误", count: 42 },
  { id: "C3", label: "解题过程缺失", count: 29 },
  { id: "C4", label: "审题偏差", count: 19 },
  { id: "C5", label: "表达不规范", count: 12 },
  { id: "C6", label: "方法选择不当", count: 8 },
];

const percent = new Intl.NumberFormat("zh-CN", {
  style: "percent", maximumFractionDigits: 1,
});

function allocateCells(rows) {
  const sorted = rows.filter(({ count }) => Number.isSafeInteger(count) && count > 0)
    .sort((a, b) => b.count - a.count || a.id.localeCompare(b.id));
  const total = sorted.reduce((sum, row) => sum + row.count, 0);
  const categories = sorted.map((row, index) => {
    const weight = row.count * 100;
    const lightness = 30 + 53 * index / Math.max(1, sorted.length - 1);
    return {
      ...row,
      share: row.count / total,
      cells: Math.floor(weight / total),
      remainder: weight % total,
      color: `hsl(213 55% ${lightness}%)`,
    };
  });
  // Distribute leftover cells by largest remainder. Keep the legend based on
  // the original counts so a small category still appears if it gets no cell.
  const remaining = 100 - categories.reduce((sum, row) => sum + row.cells, 0);
  [...categories].sort((a, b) => b.remainder - a.remainder)
    .slice(0, remaining).forEach((row) => { row.cells += 1; });
  return { categories, total };
}

export function ErrorWaffle({ rows = mockErrors }) {
  const [active, setActive] = useState(null);
  const { categories, total } = allocateCells(rows);
  if (!total) return <p className="px-2 py-3 text-sm text-slate-500">本班暂无错因记录。</p>;

  return (
    <figure aria-label="本班错因构成" className="mx-auto grid w-full max-w-[44rem] items-center gap-4 px-2 py-2 text-[#1E293B]
      min-[460px]:grid-cols-[minmax(0,10rem)_minmax(0,1fr)] sm:gap-6 sm:px-3">
      <div className="mx-auto w-full max-w-40 min-[460px]:mx-0">
        <div className="grid aspect-square grid-cols-10 grid-rows-10 gap-[2px]" aria-hidden="true">
          {categories.flatMap(({ id, cells, color }) => Array.from({ length: cells }, (_, index) => (
            <span key={`${id}-${index}`} data-category={id}
              className={`rounded-[2px] transition-opacity ${active && active !== id ? "opacity-25" : "opacity-100"}`}
              style={{ backgroundColor: color }} />
          )))}
        </div>
        <p className="mt-1.5 text-center text-xs text-slate-500">
          共 {total} 条诊断
        </p>
      </div>

      <ul className="m-0 min-w-0 list-none p-0" aria-label="错因条数与实际占比">
        {categories.map(({ id, label, count, share, color }) => (
          <li key={id} tabIndex={0}
            onMouseEnter={() => setActive(id)} onMouseLeave={() => setActive(null)}
            onFocus={() => setActive(id)} onBlur={() => setActive(null)}
            className="grid grid-cols-[auto_minmax(0,1fr)_auto_auto] items-center gap-x-2
              border-b border-slate-100 px-1 py-1.5 text-sm last:border-0 hover:bg-slate-50
              focus-visible:bg-slate-50 focus-visible:outline-2 focus-visible:outline-slate-300 sm:gap-x-4">
            <span aria-hidden="true" className="size-2.5 rounded-[2px]" style={{ backgroundColor: color }} />
            <span className="min-w-0 break-words font-medium">{label}</span>
            <span className="whitespace-nowrap text-right text-xs tabular-nums text-slate-600">{count} 条</span>
            <span className="min-w-[5ch] text-right font-mono text-xs font-semibold tabular-nums">
              {percent.format(share)}
            </span>
          </li>
        ))}
      </ul>
    </figure>
  );
}
