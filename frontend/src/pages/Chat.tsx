import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import Markdown from "../components/Markdown";

const SUGGESTIONS = [
  "Check-in: leg day squat 4x6 225, read 30 min of Psychology of Money, studied Security+ ports for 20 min",
  "What do I know so far about Zero Trust?",
  "Ingest whatever is new in my raw folder",
  "How am I doing on my reading goal this week?",
];

export default function Chat() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [chats, setChats] = useState<any[]>([]);
  const [display, setDisplay] = useState<any[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [model, setModel] = useState("claude-opus-5-5");
  const endRef = useRef<HTMLDivElement>(null);

  const loadList = () => api.chats().then(setChats);
  useEffect(() => {
    loadList();
  }, []);
  useEffect(() => {
    if (id) api.chat(id).then((c) => setDisplay(c.display));
    else setDisplay([]);
  }, [id]);
  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [display, busy]);

  const send = async (msg = text) => {
    if (!msg.trim() || busy) return;
    setText("");
    setDisplay((d) => [...d, { role: "user", text: msg }]);
    setBusy(true);
    try {
      const r = await api.sendChat(id ?? null, msg, model);
      setDisplay(r.display);
      if (!id) navigate(`/chat/${r.id}`, { replace: true });
      loadList();
    } catch (e: any) {
      setDisplay((d) => [...d, { role: "error", text: e.message }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="chat-page">
      <div className="chat-list">
        <button className="btn primary full" onClick={() => navigate("/chat")}>
          New chat +
        </button>
        {chats.map((c) => (
          <div key={c.id} className={`chat-item ${c.id === id ? "active" : ""}`} onClick={() => navigate(`/chat/${c.id}`)}>
            <span className="ellipsis">{c.title}</span>
            <button
              className="x"
              onClick={async (e) => {
                e.stopPropagation();
                await api.deleteChat(c.id);
                if (c.id === id) navigate("/chat");
                loadList();
              }}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
      <div className="chat-main">
        <div className="messages">
          {display.length === 0 && (
            <div className="empty">
              <div className="kicker">03 — Chat</div>
              <h2>What's on today?</h2>
              <p className="muted">I can log habits, answer from your Obsidian wiki, search the web, and run your workflows.</p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} className="suggestion" onClick={() => send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {display.map((m, i) => (
            <div key={i} className={`msg msg-${m.role}`}>
              {m.role === "assistant" ? <Markdown text={m.text} /> : <div className="pre">{m.text}</div>}
              {m.tools?.length > 0 && <div className="tool-trace">Tools — {m.tools.join(" · ")}</div>}
            </div>
          ))}
          {busy && <div className="msg msg-assistant typing">Thinking…</div>}
          <div ref={endRef} />
        </div>
        <div className="composer">
          <select value={model} onChange={(e) => setModel(e.target.value)} title="Model">
            <option value="claude-opus-5-5">Opus 5.5</option>
            <option value="claude-sonnet-5-5">Sonnet 5.5</option>
            <option value="claude-haiku-5-5">Haiku 5.5</option>
          </select>
          <textarea
            rows={2}
            value={text}
            placeholder="Message… (Enter to send, Shift+Enter for newline)"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <button className="btn primary" onClick={() => send()} disabled={busy}>
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

