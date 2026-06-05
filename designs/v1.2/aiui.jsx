/* Matchbox — React glue for the AI client. useStream() drives a live, calm
   generation: streams tokens in, reflects work in the ambient assistant queue. */
const { useState: useAiSt, useRef: useAiRef } = React;

function useStream() {
  const [text, setText] = useAiSt("");
  const [busy, setBusy] = useAiSt(false);
  const [source, setSource] = useAiSt(null);
  const abortRef = useAiRef(null);

  const run = async ({ system, prompt, fallback, task }) => {
    setBusy(true); setText(""); setSource(null);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const taskId = window.MBQueue && window.MBQueue.start ? window.MBQueue.start(task || "Working", "draft") : null;
    let res;
    try {
      res = await window.MBAI.stream({ system, prompt, fallback, onToken: setText, signal: ctrl.signal });
    } catch (e) { res = { text: fallback || "", source: "demo" }; setText(fallback || ""); }
    setSource(res.source);
    if (taskId && window.MBQueue.done) window.MBQueue.done(taskId);
    setBusy(false);
    return res;
  };

  const stop = () => { if (abortRef.current) abortRef.current.abort(); setBusy(false); };
  return { text, busy, source, run, stop, setText };
}

/* small label showing where the output came from */
function AISource({ source }) {
  if (!source) return null;
  const map = {
    byok: { t: "Live · your key", tone: "ok", icon: "zap" },
    claude: { t: "Live · Claude", tone: "ok", icon: "zap" },
    demo: { t: "Demo output · add a key in Settings for live AI", tone: "neutral", icon: "info" },
  };
  const m = map[source] || map.demo;
  return <span className={window.cx("mbadge", "t-" + m.tone)} style={{ fontWeight: 500 }}><Icon name={m.icon} size={11} /> {m.t}</span>;
}

window.useStream = useStream;
window.AISource = AISource;
