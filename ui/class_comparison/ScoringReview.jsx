import React from "react";
import mockRows from "../scoring_review_mock.json";
import "./styles.css";

const validRate = (rate) => Number.isFinite(rate) && rate >= 0 && rate <= 1;
const percent = new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 2 });

export function ScoringReview({ rows = mockRows }) {
  // A shared scale rounded up to the next 5 percentage points fills the
  // available space for low scores while preserving every bar's proportion.
  const ceiling = Math.max(1, Math.ceil(Math.max(0, ...rows
    .filter(({ rate }) => validRate(rate)).map(({ rate }) => rate)) * 20)) / 20;

  return (
    <ul className="m-0 w-full list-none px-2 py-1 text-[#1E293B] sm:px-3"
      role="list" aria-label={`评分步骤得分率，条长范围 0% 至 ${percent.format(ceiling)}`}>
      {rows.map(({ id, description, rate }) => {
        // Missing rates have no graphic. A scored zero is a real result.
        const observed = validRate(rate);
        const priority = observed && rate <= 0.3;
        const width = rate === 0 ? "8px" : `${rate / ceiling * 100}%`;
        return (
          <li key={id} className="grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)]
            items-center gap-3 border-b border-gray-100 py-2 last:border-b-0 sm:gap-5">
            <div className="min-w-0 text-left [overflow-wrap:anywhere]">
              <span className="block font-mono text-[11px] text-slate-500">{id}</span>
              <span className="block text-sm leading-snug text-slate-800">{description}</span>
            </div>
            {observed ? (
              <div className="min-w-0 pr-[3.75rem]">
                <span className="relative block h-1.5">
                  <span
                    aria-hidden="true"
                    className={`block h-full rounded-full ${priority ? "bg-[#F87171]" : "bg-[#60A5FA]"}`}
                    style={{ width }}
                  />
                  <span
                    className={`absolute top-1/2 -translate-y-1/2 whitespace-nowrap font-mono text-xs
                      tabular-nums ${priority ? "font-semibold text-[#B4232B]" : "text-slate-700"}`}
                    style={{ left: `calc(${width} + 8px)` }}
                  >{percent.format(rate)}</span>
                </span>
              </div>
            ) : <span className="text-xs text-slate-500">暂无数据</span>}
          </li>
        );
      })}
    </ul>
  );
}
