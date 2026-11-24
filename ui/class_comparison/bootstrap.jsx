import React from "react";
import { createRoot } from "react-dom/client";
import { ClassComparison } from "./main.jsx";

const root = createRoot(document.getElementById("root"));
if (window.parent === window) {
  root.render(<ClassComparison />);
} else {
  const send = (type, fields = {}) => window.parent.postMessage({ isStreamlitMessage: true, type, ...fields }, "*");
  window.addEventListener("message", ({ source, data }) => {
    if (source === window.parent && data?.type === "streamlit:render") {
      root.render(<ClassComparison data={data.args.dashboard} />);
    }
  });
  new ResizeObserver(([entry]) => {
    send("streamlit:setFrameHeight", { height: Math.ceil(entry.contentRect.height) });
  }).observe(document.body);
  send("streamlit:componentReady", { apiVersion: 1 });
}
