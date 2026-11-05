import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  addEdge,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";
import { api, type BlockMeta, type NodeData, type Run, type Workflow } from "../api";
import BlockNode, { BlocksContext } from "../components/BlockNode";
import Inspector from "../components/Inspector";
import RunView from "../components/RunView";

const nodeTypes = { block: BlockNode };

function defaults(meta: BlockMeta): Record<string, unknown> {
  return Object.fromEntries(meta.fields.map((f) => [f.key, f.default ?? ""]));
}

function upstream(id: string, edges: Edge[]): string[] {
  const seen = new Set<string>();
  const stack = [id];
  while (stack.length) {
    const cur = stack.pop()!;
    for (const e of edges) if (e.target === cur && !seen.has(e.source)) (seen.add(e.source), stack.push(e.source));
  }
  return [...seen];
}

function EditorInner() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { screenToFlowPosition } = useReactFlow();
  const [blocks, setBlocks] = useState<BlockMeta[]>([]);
  const [wf, setWf] = useState<Workflow | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const [runInput, setRunInput] = useState("");
  const [showRun, setShowRun] = useState(false);
  const [msg, setMsg] = useState("");
  const poll = useRef<number | null>(null);

  const metaMap = useMemo(() => Object.fromEntries(blocks.map((b) => [b.type, b])), [blocks]);

  useEffect(() => {
    api.blocks().then((r) => setBlocks(r.blocks));
    if (id === "new") {
      setWf({ id: "", name: "New workflow", description: "", enabled: true, graph: { nodes: [], edges: [] } });
      return;
    }
    api.workflow(id!).then((w) => {
      setWf(w);
      setNodes(w.graph.nodes || []);
      setEdges(w.graph.edges || []);
      const manual = (w.graph.nodes || []).find((n: any) => n.data.blockType === "trigger.manual");
      setRunInput(manual?.data?.config?.default_input ?? "");
    });
    return () => {
      if (poll.current) window.clearInterval(poll.current);
    };
  }, [id]);

  const markDirty = () => setDirty(true);

  const onConnect = useCallback(
    (c: Connection) => {
      setEdges((eds) => addEdge({ ...c, id: `e-${c.source}-${c.sourceHandle ?? "out"}-${c.target}` }, eds));
      markDirty();
    },
    [setEdges]
  );

  const newId = (type: string) => {
    const base = type.split(".").pop()!.replace(/[^a-z0-9]/gi, "");
    let i = 1;
    while (nodes.some((n) => n.id === `${base}_${i}`)) i++;
    return `${base}_${i}`;
  };

  const addBlock = (meta: BlockMeta, position?: { x: number; y: number }) => {
    const nid = newId(meta.type);
    const pos = position ?? screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 });
    const data: NodeData = { blockType: meta.type, label: meta.name, config: defaults(meta) };
    setNodes((ns) => [...ns, { id: nid, type: "block", position: pos, data }]);
    setSelected(nid);
    markDirty();
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const type = e.dataTransfer.getData("application/sims-block");
    const meta = metaMap[type];
    if (meta) addBlock(meta, screenToFlowPosition({ x: e.clientX, y: e.clientY }));
  };

  const serialize = (): Workflow => ({
    ...wf!,
    graph: {
      nodes: nodes.map(({ id, type, position, data }) => {
        const { _status, ...rest } = data as any;
        return { id, type, position, data: rest };
      }),
      edges: edges.map(({ id, source, target, sourceHandle }) => ({ id, source, target, sourceHandle })),
    },
  });

  const save = async () => {
    const saved = await api.saveWorkflow({ ...serialize(), id: wf!.id || undefined });
    setWf(saved);
    setDirty(false);
    setMsg("Saved");
    setTimeout(() => setMsg(""), 1500);
    if (id === "new") navigate(`/workflows/${saved.id}`, { replace: true });
    return saved;
  };

  const paintStatus = (r: Run) => {
    const st = Object.fromEntries((r.steps ?? []).map((s) => [s.node_id, s.status]));
    setNodes((ns) => ns.map((n) => ({ ...n, data: { ...n.data, _status: st[n.id] ?? "idle" } })));
  };

  const runNow = async () => {
    const saved = dirty || !wf!.id ? await save() : wf!;
    const { run_id } = await api.runWorkflow(saved.id, runInput);
    setShowRun(true);
    if (poll.current) window.clearInterval(poll.current);
    const tick = async () => {
      const r = await api.run(run_id);
      setRun(r);
      paintStatus(r);
      if (r.status !== "running" && poll.current) {
        window.clearInterval(poll.current);
        poll.current = null;
      }
    };
    await tick();
    poll.current = window.setInterval(tick, 1200);
  };

  const remove = async () => {
    if (!wf?.id || !confirm(`Delete workflow "${wf.name}"?`)) return;
    await api.deleteWorkflow(wf.id);
    navigate("/workflows");
  };

  const sel = nodes.find((n) => n.id === selected);
  const categories = useMemo(() => {
    const m: Record<string, BlockMeta[]> = {};
    blocks.forEach((b) => (m[b.category] ??= []).push(b));
    return m;
  }, [blocks]);

  if (!wf) return <div className="page">Loading…</div>;

  return (
    <BlocksContext.Provider value={metaMap}>
      <div className="editor">
        <div className="editor-bar">
          <input
            className="title-input"
            value={wf.name}
            onChange={(e) => (setWf({ ...wf, name: e.target.value }), markDirty())}
          />
          <label className="check">
            <input type="checkbox" checked={wf.enabled} onChange={(e) => (setWf({ ...wf, enabled: e.target.checked }), markDirty())} />
            Enabled (schedules & folder watch)
          </label>
          <div className="grow" />
          {msg && <span className="muted small">{msg}</span>}
          <input className="run-input" placeholder="Run input ({{input}})" value={runInput} onChange={(e) => setRunInput(e.target.value)} />
          <button className="btn" onClick={save} disabled={!dirty && !!wf.id}>
            {dirty || !wf.id ? "Save" : "Saved"}
          </button>
          <button className="btn primary" onClick={runNow} disabled={run?.status === "running"}>
            {run?.status === "running" ? "Running…" : "Run →"}
          </button>
          <button className="btn ghost" onClick={() => setShowRun((s) => !s)}>
            Log
          </button>
          {wf.id && (
            <button className="btn ghost danger-text" onClick={remove} title="Delete workflow">
              Delete
            </button>
          )}
        </div>
        <textarea
          className="desc-input"
          rows={1}
          placeholder="Description"
          value={wf.description}
          onChange={(e) => (setWf({ ...wf, description: e.target.value }), markDirty())}
        />

        <div className="editor-body">
          <div className="palette">
            {Object.entries(categories).map(([cat, list]) => (
              <div key={cat}>
                <div className="palette-cat">{cat}</div>
                {list.map((b) => (
                  <div
                    key={b.type}
                    className="palette-item"
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData("application/sims-block", b.type)}
                    onClick={() => addBlock(b)}
                    title={b.description}
                    style={{ ["--accent" as any]: b.color }}
                  >
                    <span className="code">{b.icon}</span> {b.name}
                  </div>
                ))}
              </div>
            ))}
            <p className="muted small">Drag or click to add. Connect the right handle to the left handle.</p>
          </div>

          <div className="canvas" onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              onNodesChange={(c) => {
                onNodesChange(c);
                if (c.some((x) => x.type === "position" || x.type === "remove")) markDirty();
              }}
              onEdgesChange={(c) => {
                onEdgesChange(c);
                if (c.some((x) => x.type === "remove")) markDirty();
              }}
              onConnect={onConnect}
              onNodeClick={(_, n) => setSelected(n.id)}
              onPaneClick={() => setSelected(null)}
              defaultEdgeOptions={{ type: "smoothstep", style: { strokeWidth: 1.25 } }}
              deleteKeyCode={["Delete"]}
              fitView
              colorMode="light"
            >
              <Background variant={BackgroundVariant.Lines} gap={24} />
              <Controls />
              <MiniMap pannable zoomable />
            </ReactFlow>
          </div>

          {sel && (
            <Inspector
              key={sel.id}
              nodeId={sel.id}
              data={sel.data as unknown as NodeData}
              meta={metaMap[(sel.data as any).blockType]}
              variables={upstream(sel.id, edges)}
              onChange={(data) => {
                setNodes((ns) => ns.map((n) => (n.id === sel.id ? { ...n, data: { ...data, _status: (n.data as any)._status } } : n)));
                markDirty();
              }}
              onDelete={() => {
                setNodes((ns) => ns.filter((n) => n.id !== sel.id));
                setEdges((es) => es.filter((e) => e.source !== sel.id && e.target !== sel.id));
                setSelected(null);
                markDirty();
              }}
            />
          )}
        </div>

        {showRun && (
          <div className="run-drawer">
            <div className="drawer-head">
              <b>Run log</b>
              <button className="btn ghost" onClick={() => setShowRun(false)}>
                ✕
              </button>
            </div>
            {run ? <RunView run={run} /> : <p className="muted">Click ▶ Run to execute this workflow.</p>}
          </div>
        )}
      </div>
    </BlocksContext.Provider>
  );
}

export default function Editor() {
  return (
    <ReactFlowProvider>
      <EditorInner />
    </ReactFlowProvider>
  );
}
