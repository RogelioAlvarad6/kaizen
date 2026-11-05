import { createContext, memo, useContext } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { BlockMeta, NodeData } from "../api";

export const BlocksContext = createContext<Record<string, BlockMeta>>({});

function summary(meta: BlockMeta | undefined, cfg: Record<string, unknown>): string {
  if (!meta) return "";
  if (cfg.cron) return `⏰ ${cfg.cron}`;
  if (cfg.model) return String(cfg.model).replace("claude-", "") + (cfg.effort ? ` · ${cfg.effort}` : "");
  if (cfg.path) return String(cfg.path);
  if (cfg.mode && cfg.value !== undefined) return `${cfg.mode} "${cfg.value}"`;
  if (cfg.days) return `${cfg.days} days`;
  return meta.category;
}

function BlockNode({ id, data, selected }: NodeProps) {
  const d = data as unknown as NodeData & { _status?: string };
  const meta = useContext(BlocksContext)[d.blockType];
  const color = meta?.color ?? "#64748b";
  const outputs = meta?.outputs ?? ["out"];
  return (
    <div className={`block-node ${selected ? "selected" : ""} status-${d._status ?? "idle"}`} style={{ ["--accent" as any]: color }}>
      {!meta?.is_trigger && <Handle type="target" position={Position.Left} />}
      <div className="block-head">
        <span className="block-icon">{meta?.icon ?? "?"}</span>
        <div className="block-titles">
          <div className="block-label">{d.label || meta?.name}</div>
          <div className="block-type">
            {meta?.name ?? d.blockType} · <code>{id}</code>
          </div>
        </div>
        {d._status && d._status !== "idle" && <span className={`dot dot-${d._status}`} />}
      </div>
      <div className="block-body">{summary(meta, d.config || {})}</div>
      {outputs.length === 1 ? (
        <Handle type="source" position={Position.Right} id={outputs[0]} />
      ) : (
        outputs.map((o, i) => (
          <div key={o}>
            <Handle type="source" position={Position.Right} id={o} style={{ top: `${((i + 1) / (outputs.length + 1)) * 100}%` }} />
            <span className={`handle-label handle-${o}`} style={{ top: `calc(${((i + 1) / (outputs.length + 1)) * 100}% - 8px)` }}>
              {o}
            </span>
          </div>
        ))
      )}
    </div>
  );
}

export default memo(BlockNode);
