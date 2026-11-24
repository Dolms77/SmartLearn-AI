# 班级对比

`main.jsx` 导出 `ClassComparison` 和 `mockData`。组件通过 `data` 接收主题、班级、指标和题目数据，得分率使用 0 到 1 的比例。空缺主题得分使用 `null`。题目圆点大小按作答记录数区分。

`ScoringReview.jsx` 导出评分步骤列表。每行包含 `id`、`description` 和 `rate`；`null` 显示「暂无数据」，有效的 0% 显示红色胶囊。独立预览在开发服务器的网址后加 `?view=scoring-review`，会加载 `../scoring_review_mock.json`。

`ErrorWaffle.jsx` 导出错因构成图和 `mockErrors`。每项包含 `id`、`label` 和 `count`。独立预览使用 `?view=error-waffle`。

在本目录运行 `npm ci` 和 `npm run build` 会生成 `dist/`。开发预览可运行 `npx vite`，独立预览默认使用模拟数据。Streamlit 通过 `bootstrap.jsx` 传入实际数据，并按内容高度调整 iframe。

`dist/` 随项目提交，普通用户可以直接运行项目的界面启动脚本。
