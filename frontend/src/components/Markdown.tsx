import { marked } from "marked";
import { useMemo } from "react";

// Renders model output as markdown. Raw HTML in the text is escaped, not rendered.
const renderer = new marked.Renderer();
renderer.html = ({ text }) => text.replace(/</g, "&lt;").replace(/>/g, "&gt;");

export default function Markdown({ text }: { text: string }) {
  const html = useMemo(() => marked.parse(text || "", { renderer, async: false }) as string, [text]);
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />;
}
