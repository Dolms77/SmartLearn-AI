import React from "react";
import { mockMastery } from "./StudentMastery.jsx";
import "./styles.css";

const slots = [1, 2, 3, 4, 5];
const mockCounts = [5, 2, 0, 3, 4, 1, 8, 2, 3];
export const mockEvidence = mockMastery.map(({ code, name }, index) => ({
  id: code, name, count: mockCounts[index],
}));

export function EvidenceDotMatrix({ rows = mockEvidence, threshold = 3 }) {
  return (
    <section aria-labelledby="evidence-matrix" className="w-full px-2 py-2 text-slate-800 sm:px-3">
      <h2 id="evidence-matrix">各指标的有效作答记录</h2>
      <p className="mt-1 text-xs leading-relaxed text-slate-600">
        每个圆点代表 1 条有效作答。满 {threshold} 条才判断掌握度。
        {rows.some(({ count }) => count > slots.length) && " 点阵最多显示 5 格，实际条数见指标下方。"}
      </p>

      <div className="relative isolate mt-4 grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-x-3">
        <div className="pb-2 text-xs font-medium text-slate-500">指标</div>
        <div className="relative pb-2 text-xs text-slate-600">
          <span className="absolute -translate-x-1/2 whitespace-nowrap"
            style={{ left: `${threshold / slots.length * 100}%` }}>门槛：{threshold} 条</span>
        </div>
        {rows.length > 0 && (
          <div aria-hidden="true" className="pointer-events-none relative col-start-2 self-stretch"
            style={{ gridRow: `2 / span ${rows.length}` }}>
            <div className="absolute inset-y-0 border-l border-dashed border-[#9CA3AF]"
              style={{ left: `${threshold / slots.length * 100}%` }} />
          </div>
        )}

        {rows.map(({ id, name, count }, index) => {
          const enough = count >= threshold;
          const status = enough ? "证据充足" : "证据不足";
          return (
            <div key={id} tabIndex={0} aria-label={`${name}，${count} 条有效作答，${status}`}
              className="group relative col-span-2 col-start-1 grid grid-cols-subgrid items-center rounded-sm py-2
                outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
              style={{ gridRow: index + 2 }}>
              <div className="min-w-0 text-left [overflow-wrap:anywhere]">
                <div className="text-sm leading-snug">{name}</div>
                <div className="mt-0.5 text-xs tabular-nums text-slate-500">{count} 条 · {status}</div>
              </div>
              <div aria-hidden="true" className="grid grid-cols-5 justify-items-center">
                {slots.map((slot) => (
                  <span key={slot} data-filled={slot <= count}
                    className={`size-2.5 rounded-full border sm:size-3 ${slot > count
                      ? "border-[#E5E7EB]"
                      : enough ? "border-[#10B981] bg-[#10B981]" : "border-[#F87171] bg-[#F87171]"}`} />
                ))}
              </div>
              <div role="tooltip"
                className={`pointer-events-none absolute right-0 z-10 hidden max-w-full rounded-lg
                  border border-slate-100 bg-white px-3 py-2 text-xs leading-relaxed text-slate-700
                  shadow-md group-hover:block group-focus:block ${index === 0 ? "top-full" : "bottom-full"}`}>
                <strong>{id} · {name}</strong>
                <div>有效作答 {count} 条 · {status}</div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
