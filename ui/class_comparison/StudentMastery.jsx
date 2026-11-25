import React, { useState } from "react";
import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer } from "recharts";
import "./styles.css";

export const mockMastery = [
  { code: "T01I1", name: "表示数量关系并代入求值", mastery: 0.46, n: 7 },
  { code: "T01I2", name: "合并同类项与整式化简", mastery: 0.5, n: 8 },
  { code: "T01I3", name: "用代数式解释实际问题", mastery: null, n: 1 },
  { code: "T02I1", name: "根据题意建立方程", mastery: 0.79, n: 8 },
  { code: "T02I2", name: "求解一元一次方程", mastery: 0.8, n: 10 },
  { code: "T02I3", name: "检验解的合理性", mastery: 0, n: 5 },
  { code: "T03I1", name: "运用不等式性质求解", mastery: 0.91, n: 10 },
  { code: "T03I2", name: "用数轴表示不等式解集", mastery: null, n: 0 },
  { code: "T03I3", name: "解释不等式的实际意义", mastery: 1, n: 9 },
];

const rings = [0.25, 0.5, 0.75, 1];
const navy = "#234773";
const shortNames = {
  T01I1: "代入求值", T01I2: "整式化简", T01I3: "整式应用",
  T02I1: "解一元方程", T02I2: "方程组消元", T02I3: "列式与检验",
  T03I1: "不等式性质", T03I2: "解集交集", T03I3: "解释取值范围",
};
const valid = (rate) => Number.isFinite(rate) && rate >= 0 && rate <= 1;
const format = new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 1 });
const rateText = (row) => valid(row.mastery) ? format.format(row.mastery) : "证据不足";
const bands = { mastered: "已掌握", developing: "发展中", weak: "薄弱" };
const detail = (row) => [
  `${row.code} ${row.name}`, rateText(row), `作答 ${row.n} 条`, bands[row.band],
].filter(Boolean).join("，");

function Tooltip({ row, className = "" }) {
  return (
    <div role="tooltip" className={`pointer-events-none absolute z-10 w-max max-w-[min(15rem,100%)]
      rounded-lg border border-slate-100 bg-white px-3 py-2 text-xs leading-relaxed
      text-slate-600 shadow-md ${className}`}>
      <strong className="font-semibold text-slate-800">{row.name}</strong>
      <br />{row.code} · {rateText(row)} · 作答 {row.n} 条
      {bands[row.band] && <><br />掌握度判定：{bands[row.band]}</>}
    </div>
  );
}

function RadarLabel({ x, y, textAnchor, payload, rows, setActive }) {
  const row = rows.find(({ code }) => code === payload.value);
  if (!row) return null;
  const name = shortNames[row.code] ?? row.name;
  const above = textAnchor === "middle" && payload.coordinate === 90;
  return (
    <g tabIndex={0} aria-label={detail(row)}
      onMouseEnter={() => setActive(row)} onMouseLeave={() => setActive(null)}
      onFocus={() => setActive(row)} onBlur={() => setActive(null)}>
      <text x={x} y={above ? y - 15 : y - 5}
        textAnchor={textAnchor} fill="#334155" fontSize={10.5}>
        <tspan>{name}</tspan>
        <tspan x={x} dy={12} fill="#46566c" fontSize={9}>{row.code}</tspan>
      </text>
    </g>
  );
}

function RadarProfile({ points = [], setActive }) {
  return (
    <g>
      {points.map((point, i) => {
        const next = points[(i + 1) % points.length];
        // Missing values break the profile. A valid zero remains at the center.
        if (!valid(point.value) || !valid(next.value)) return null;
        return <line key={point.payload.code} data-profile-line="" x1={point.x} y1={point.y}
          x2={next.x} y2={next.y} stroke={navy} strokeWidth={2} strokeLinecap="round" />;
      })}
      {points.filter((point) => valid(point.value)).map(({ x, y, payload }) => (
        <g key={payload.code} tabIndex={0} aria-label={detail(payload)}
          onMouseEnter={() => setActive(payload)} onMouseLeave={() => setActive(null)}
          onFocus={() => setActive(payload)} onBlur={() => setActive(null)}>
          <circle cx={x} cy={y} r={9} fill="transparent" />
          <circle cx={x} cy={y} r={3.5} fill={navy} data-mastery-vertex="" />
        </g>
      ))}
    </g>
  );
}

function KnowledgeRadar({ rows }) {
  const [active, setActive] = useState(null);
  return (
    <section aria-labelledby="knowledge-radar" className="min-w-0">
      <h2 id="knowledge-radar">知识点掌握度</h2>
      <div className="relative h-[21rem] min-w-0 sm:h-[24rem]">
        <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 320, height: 336 }}>
          <RadarChart data={rows} cx="50%" cy="51%" outerRadius="49%">
            <PolarGrid gridType="circle" radialLines={false} stroke="#F0F0F0" />
            <PolarAngleAxis dataKey="code" axisLine={false} tickLine={false} tickSize={12}
              tick={(props) => <RadarLabel {...props} rows={rows} setActive={setActive} />} />
            <PolarRadiusAxis domain={[0, 1]} ticks={rings} tick={false} tickLine={false} axisLine={false} />
            <Radar dataKey="mastery" isAnimationActive={false}
              shape={(props) => <RadarProfile {...props} setActive={setActive} />} />
          </RadarChart>
        </ResponsiveContainer>
        {active && <Tooltip row={active} className="left-1/2 top-1 -translate-x-1/2" />}
      </div>
      {rows.some(({ mastery }) => !valid(mastery)) &&
        <p className="text-xs text-slate-500">证据不足的指标仅显示名称，折线在该处断开。</p>}
    </section>
  );
}

function IndicatorLollipops({ rows }) {
  return (
    <section aria-labelledby="indicator-lollipops" className="min-w-0">
      <h2 id="indicator-lollipops">具体指标掌握度</h2>
      <div className="mt-3">
        {rows.map((row, i) => {
          const { code, name, mastery } = row;
          const known = valid(mastery);
          const color = mastery < 0.5 ? "#F87171" : mastery < 0.8 ? "#FBBF24" : "#34D399";
          return (
            <div key={code} tabIndex={0} aria-label={detail(row)}
              className="group relative grid min-h-9 grid-cols-[minmax(0,1.28fr)_minmax(0,1fr)]
                items-center gap-3 py-1">
              <div className="min-w-0 text-left text-xs leading-snug text-slate-700 [overflow-wrap:anywhere]">{name}</div>
              <div className="mr-12">
                <div className="relative flex h-4 items-center">
                  {known ? <>
                    <div aria-hidden="true" className="h-px w-full bg-slate-200" />
                    <span className="absolute size-3 -translate-x-1/2 rounded-full"
                      style={{ left: `${mastery * 100}%`, backgroundColor: color }} data-score-point="" />
                    <span className="absolute whitespace-nowrap font-mono text-xs tabular-nums text-slate-700"
                      style={{ left: `calc(${mastery * 100}% + 10px)` }}>{format.format(mastery)}</span>
                  </> : <>
                    <div aria-hidden="true" className="h-[5px] w-full
                      bg-[repeating-linear-gradient(135deg,#e2e8f0_0px,#e2e8f0_1px,transparent_1px,transparent_4px)]" data-missing-track="" />
                    <span className="absolute left-full ml-2 whitespace-nowrap text-[10px] text-slate-500">暂无数据</span>
                  </>}
                </div>
              </div>
              <Tooltip row={row} className={`right-0 hidden group-hover:block group-focus:block
                ${i < 2 ? "top-full" : "bottom-full"}`} />
            </div>
          );
        })}
        <div className="grid grid-cols-[minmax(0,1.28fr)_minmax(0,1fr)] gap-3" aria-hidden="true">
          <div className="relative col-start-2 mr-12 mt-1 h-5 border-t border-slate-200">
            {[0, .25, .5, .75, 1].map((tick) => (
              <span key={tick} className={`absolute top-1 -translate-x-1/2 font-mono text-[9px] text-slate-500
                ${tick === .25 || tick === .75 ? "hidden min-[380px]:inline" : ""}`}
                style={{ left: format.format(tick) }}>{format.format(tick)}</span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export function StudentMastery({ rows = mockMastery }) {
  return (
    <main className="grid w-full gap-5 px-2 pb-3 pt-2 text-[#1E293B]
      min-[720px]:grid-cols-[minmax(0,1fr)_minmax(0,1.18fr)] sm:px-4">
      <KnowledgeRadar rows={rows} />
      <IndicatorLollipops rows={rows} />
    </main>
  );
}
