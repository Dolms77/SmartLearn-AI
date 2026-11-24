import React from "react";
import "./styles.css";

export const mockData = {
  topics: ["代数式", "方程", "不等式"],
  classes: [
    { id: "DC01", rates: [0.46, 0.585, 0.643] },
    { id: "DC02", rates: [0.52, 0.612, null] },
  ],
  indicators: [
    { id: "T01I1", label: "表示数量关系并代入求值", rate: 0.46, count: 51 },
    { id: "T01I2", label: "合并同类项与整式化简", rate: 0.58, count: 43 },
    { id: "T03I1", label: "运用不等式性质求解", rate: 0.72, count: 38 },
  ],
  questions: [
    { id: "Q028", label: "列出方程并求解", rate: 0.12, count: 12 },
    { id: "Q037", label: "写出不等式的解集", rate: 0.2857, count: 7 },
    { id: "Q002", label: "把已知数值代入代数式", rate: 0.3077, count: 13 },
  ],
};

const percent = (rate, digits = 0) => `${(rate * 100).toFixed(digits)}%`;
const sorted = (data) => [...data].filter((row) => Number.isFinite(row.rate))
  .sort((a, b) => a.rate - b.rate);

function Tooltip({ children, className = "" }) {
  return (
    <span role="tooltip" className={`pointer-events-none absolute z-20 hidden w-max max-w-52
      rounded-md border border-slate-100 bg-white px-3 py-2 text-left text-xs font-normal
      leading-relaxed text-slate-600 shadow-lg group-hover:block group-focus-within:block ${className}`}>
      {children}
    </span>
  );
}

function ThemeScores({ topics, classes }) {
  return (
    <section aria-labelledby="theme-scores">
      <h2 id="theme-scores">各班主题得分率</h2>
      {classes.length ? (
        <table className="mt-3 w-full table-fixed border-collapse text-left">
          <thead>
            <tr className="border-b border-slate-200 text-xs text-slate-600">
              <th scope="col" className="py-2 font-medium">班级</th>
              {topics.map((topic) => <th key={topic} scope="col" className="py-2 pl-2 font-medium">{topic}</th>)}
            </tr>
          </thead>
          <tbody>
            {classes.map(({ id, rates }) => (
              <tr key={id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/60">
                <th scope="row" className="py-2.5 font-mono text-sm font-medium">{id}</th>
                {topics.map((topic, index) => {
                  const rate = rates[index];
                  if (!Number.isFinite(rate)) {
                    return <td key={topic} className="pl-2 text-xs text-slate-500">暂无数据</td>;
                  }
                  const band = rate < 0.5 ? "low" : rate <= 0.6 ? "mid" : "high";
                  return (
                    <td key={topic} className="group relative py-2.5 pl-2 pr-3">
                      <span className={`theme-score ${band} block font-mono text-lg font-semibold tracking-tight sm:text-xl`}
                        tabIndex={0} aria-label={`${id} · ${topic}得分率 ${percent(rate, 1)}`}>
                        {percent(rate, 1)}
                        <span aria-hidden="true" className="mt-1 block h-px opacity-60"
                          style={{ width: percent(rate, 2) }} />
                      </span>
                      <Tooltip className="right-0 top-full">
                        <strong className="font-semibold text-slate-800">{id} · {topic}</strong>
                        <br />得分率 {percent(rate, 1)}
                      </Tooltip>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="mt-3 text-sm text-slate-500">暂无班级主题得分率。</p>}
    </section>
  );
}

function IndicatorRanking({ indicators }) {
  const rows = sorted(indicators);
  return (
    <section aria-labelledby="indicator-ranking" className="min-w-0">
      <h2 id="indicator-ranking">指标得分率排行</h2>
      {rows.length ? (
        <div className="mt-3 grid grid-cols-[minmax(0,1.42fr)_minmax(0,1fr)] items-center gap-x-2 gap-y-1.5">
          {rows.map(({ id, label, rate, count }) => (
            <React.Fragment key={id}>
              <span className="break-words py-0.5 text-xs leading-snug">{label}</span>
              <div className="group relative mx-2 h-6" tabIndex={0}
                aria-label={`${label}，得分率 ${percent(rate, 1)}，${count} 条作答`}>
                <span aria-hidden="true" className="absolute top-1/2 h-px bg-slate-200"
                  style={{ width: percent(rate, 2) }} />
                <span aria-hidden="true" className={`absolute top-1/2 size-2.5 -translate-x-1/2
                  -translate-y-1/2 rounded-full ${rate < 0.5 ? "bg-[#C05A5D]" : "bg-[#326B92]"}`}
                  style={{ left: percent(rate, 2) }} />
                <Tooltip className="right-0 top-full">
                  <strong className="font-semibold text-slate-800">{label}</strong>
                  <br />{percent(rate, 1)} · {count} 条作答
                </Tooltip>
              </div>
            </React.Fragment>
          ))}
          <div aria-hidden="true" className="relative col-start-2 mx-2 mt-2 h-4 font-mono text-[10px] text-slate-500">
            {[0, 50, 100].map((tick) => (
              <span key={tick} className="absolute -translate-x-1/2" style={{ left: `${tick}%` }}>{tick}%</span>
            ))}
          </div>
        </div>
      ) : <p className="mt-3 text-sm text-slate-500">暂无指标得分率。</p>}
    </section>
  );
}

function QuestionDots({ questions }) {
  const rows = sorted(questions);
  const ceiling = Math.min(1, Math.max(0.3, Math.ceil(Math.max(0, ...rows.map((row) => row.rate)) * 10) / 10));
  return (
    <section aria-labelledby="question-dots" className="min-w-0">
      <h2 id="question-dots">低得分题目分布</h2>
      {rows.length ? <>
        <div className="mt-2 flex flex-wrap justify-end gap-x-3 gap-y-1 text-[11px] text-slate-600">
          <span className="inline-flex items-center gap-1.5"><i className="size-4 rounded-full bg-[#326B92]" />10 条及以上</span>
          <span className="inline-flex items-center gap-1.5"><i className="size-2 rounded-full bg-[#326B92]/65" />5–9 条</span>
        </div>
        <div className="mt-6 grid h-52 border-b border-slate-200"
          style={{ gridTemplateColumns: `repeat(${rows.length}, minmax(0, 1fr))` }}>
          {rows.map(({ id, label, rate, count }, index) => (
            <div key={id} className="group relative" tabIndex={0}
              aria-label={`${id}，${label}，得分率 ${percent(rate, 1)}，${count} 条作答`}>
              <span className="absolute left-1/2"
                style={{ bottom: percent(rate / ceiling * 0.81, 2) }}>
                <span className="absolute bottom-3 -translate-x-1/2 font-mono text-[10px] font-medium text-slate-700">
                  {percent(rate)}
                </span>
                <span className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full
                  ${count >= 10 ? "size-4 bg-[#326B92]" : "size-2 bg-[#326B92]/65"}`} />
              </span>
              <span aria-hidden="true" className="absolute left-1/2 top-full mt-2.5 -translate-x-1/2
                whitespace-nowrap font-mono text-[10px] text-slate-600">{id}</span>
              <Tooltip className={`top-2 ${index < rows.length / 2 ? "left-0" : "right-0"}`}>
                <strong className="font-semibold text-slate-800">{id} · {label}</strong>
                <br />{percent(rate, 1)} · {count} 条作答
              </Tooltip>
            </div>
          ))}
        </div>
        <p className="mt-8 text-right text-[11px] text-slate-500">按得分率从低到高排列</p>
      </> : <p className="mt-3 text-sm text-slate-500">暂无作答达到 5 条的题目。</p>}
    </section>
  );
}

export function ClassComparison({ data = mockData }) {
  return (
    <main className="mx-auto max-w-screen-xl px-2 pb-5 pt-2 text-[#1E293B] sm:px-4">
      <ThemeScores topics={data.topics} classes={data.classes} />
      <div className="mt-5 grid gap-x-8 gap-y-6 border-t border-slate-200 pt-5 md:grid-cols-2">
        <IndicatorRanking indicators={data.indicators} />
        <QuestionDots questions={data.questions} />
      </div>
    </main>
  );
}
