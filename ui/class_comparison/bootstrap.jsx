import React from "react";
import { createRoot } from "react-dom/client";
import { ClassComparison } from "./main.jsx";
import { ScoringReview } from "./ScoringReview.jsx";

const root = createRoot(document.getElementById("root"));
if (window.parent === window) {
  const review = new URLSearchParams(window.location.search).get("view") === "scoring-review";
  root.render(review ? <ScoringReview /> : <ClassComparison />);
} else {
  const send = (type, fields = {}) => window.parent.postMessage({ isStreamlitMessage: true, type, ...fields }, "*");
  window.addEventListener("message", ({ source, data }) => {
    if (source === window.parent && data?.type === "streamlit:render") {
      const { dashboard, scoringRows } = data.args;
      root.render(Array.isArray(scoringRows)
        ? <ScoringReview rows={scoringRows} />
        : <ClassComparison data={dashboard} />);
    }
  });
  new ResizeObserver(([entry]) => {
    send("streamlit:setFrameHeight", { height: Math.ceil(entry.contentRect.height) });
  }).observe(document.body);
  send("streamlit:componentReady", { apiVersion: 1 });
}
