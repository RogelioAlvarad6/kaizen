import type { BlockMeta, Field, NodeData } from "../api";

type Props = {
  nodeId: string;
  data: NodeData;
  meta?: BlockMeta;
  variables: string[];
  onChange: (data: NodeData) => void;
  onDelete: () => void;
};

export default function Inspector({ nodeId, data, meta, variables, onChange, onDelete }: Props) {
  const cfg = data.config || {};
  const set = (key: string, value: unknown) => onChange({ ...data, config: { ...cfg, [key]: value } });

  return (
    <div className="inspector">
      <div className="inspector-head" style={{ borderColor: meta?.color }}>
        <span className="block-icon">{meta?.icon}</span>
        <div>
          <div className="muted small">{meta?.name}</div>
          <code className="small">{`{{${nodeId}}}`}</code>
        </div>
      </div>
      <p className="muted small">{meta?.description}</p>

      <label className="field">
        <span>Label</span>
        <input value={data.label} onChange={(e) => onChange({ ...data, label: e.target.value })} />
      </label>

      {meta?.fields.map((f) => (
        <FieldInput key={f.key} field={f} value={cfg[f.key] ?? f.default} onChange={(v) => set(f.key, v)} />
      ))}

      <div className="vars">
        <div className="muted small">Variables you can use in text fields:</div>
        {["input", "prev", "today", "now", "week", ...variables].map((v) => (
          <code key={v} className="var-chip" title="Click to copy" onClick={() => navigator.clipboard?.writeText(`{{${v}}}`)}>
            {`{{${v}}}`}
          </code>
        ))}
      </div>

      <button className="btn danger" onClick={onDelete}>
        Delete block
      </button>
    </div>
  );
}

function FieldInput({ field, value, onChange }: { field: Field; value: unknown; onChange: (v: unknown) => void }) {
  let input;
  switch (field.type) {
    case "textarea":
      input = <textarea rows={field.key === "system" ? 10 : 5} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />;
      break;
    case "number":
      input = <input type="number" value={Number(value ?? 0)} onChange={(e) => onChange(Number(e.target.value))} />;
      break;
    case "bool":
      input = <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />;
      break;
    case "select":
      input = (
        <select value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>
          {field.options?.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      );
      break;
    case "multiselect": {
      const arr = Array.isArray(value) ? (value as string[]) : [];
      input = (
        <div className="checks">
          {field.options?.map((o) => (
            <label key={o.value} className="check">
              <input
                type="checkbox"
                checked={arr.includes(o.value)}
                onChange={(e) => onChange(e.target.checked ? [...arr, o.value] : arr.filter((x) => x !== o.value))}
              />
              {o.label}
            </label>
          ))}
        </div>
      );
      break;
    }
    default:
      input = <input value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />;
  }
  return (
    <label className={`field ${field.type === "bool" ? "field-inline" : ""}`}>
      <span>{field.label}</span>
      {input}
      {field.help && <small className="muted">{field.help}</small>}
    </label>
  );
}
