import React from "react";
import { createRoot } from "react-dom/client";
import { ClassComparison } from "./main.jsx";
import { ScoringReview } from "./ScoringReview.jsx";
import { ErrorWaffle } from "./ErrorWaffle.jsx";
import { StudentMastery } from "./StudentMastery.jsx";

const root = createRoot(document.getElementById("root"));
if (window.parent === window) {
  const view = new URLSearchParams(window.location.search).get("view");
  if (view === "scoring-review") root.render(<ScoringReview />);
  else if (view === "error-waffle") root.render(<ErrorWaffle />);
  else if (view === "student-mastery") root.render(<StudentMastery />);
  else root.render(<ClassComparison />);
} else {
  const send = (type, fields = {}) => window.parent.postMessage({ isStreamlitMessage: true, type, ...fields }, "*");
  window.addEventListener("message", ({ source, data }) => {
    if (source === window.parent && data?.type === "streamlit:render") {
      const { dashboard, scoringRows, errorRows, masteryRows } = data.args;
      if (Array.isArray(scoringRows)) root.render(<ScoringReview rows={scoringRows} />);
      else if (Array.isArray(errorRows)) root.render(<ErrorWaffle rows={errorRows} />);
      else if (Array.isArray(masteryRows)) root.render(<StudentMastery rows={masteryRows} />);
      else root.render(<ClassComparison data={dashboard} />);
    }
  });
  new ResizeObserver(([entry]) => {
    send("streamlit:setFrameHeight", { height: Math.ceil(entry.contentRect.height) });
  }).observe(document.body);
  send("streamlit:componentReady", { apiVersion: 1 });
}
