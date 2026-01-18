import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github-dark.css";
import type {
  MessageContent,
  MessagePartImageUrl,
  MessagePartText,
} from "../types";
import { cn } from "../lib/cn";
import { Check, Copy } from "lucide-react";

function splitContent(content: MessageContent): { text: string; images: string[] } {
  if (typeof content === "string") {
    return { text: content, images: [] };
  }
  const texts: string[] = [];
  const images: string[] = [];
  for (const part of content) {
    if ((part as MessagePartText).type === "text") {
      const t = (part as MessagePartText).text;
      if (t) texts.push(t);
    } else if ((part as MessagePartImageUrl).type === "image_url") {
      const url = (part as MessagePartImageUrl).image_url?.url;
      if (url) images.push(url);
    }
  }
  return { text: texts.join("\n\n"), images };
}

function reactNodeToText(node: React.ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(reactNodeToText).join("");
  if (React.isValidElement(node)) return reactNodeToText((node.props as any)?.children);
  return "";
}

export interface MarkdownMessageProps {
  content: MessageContent;
  className?: string;
}

export const MarkdownMessage: React.FC<MarkdownMessageProps> = ({
  content,
  className,
}) => {
  const { text, images } = splitContent(content);
  const [copiedCodeValue, setCopiedCodeValue] = useState<string | null>(null);

  return (
    <div className={cn("space-y-3", className)}>
      {text && (
        <ReactMarkdown
          className="prose prose-invert max-w-none prose-pre:mt-2 prose-pre:bg-slate-900 prose-pre:border prose-pre:border-slate-700"
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeHighlight as any]}
          components={{
            code({ inline, className, children, ...props }) {
              const value = reactNodeToText(children).replace(/\n$/, "");
              const isCopied = copiedCodeValue === value;


              if (inline) {
                return (
                  <code
                    className={cn(
                      "rounded bg-slate-900 px-1 py-0.5 text-xs",
                      className
                    )}
                    {...props}
                  >
                    {children}
                  </code>
                );
              }

              async function handleCopy() {
                try {
                  await navigator.clipboard.writeText(value);
                  setCopiedCodeValue(value);
                  window.setTimeout(() => {
                    setCopiedCodeValue((cur) => (cur === value ? null : cur));
                  }, 900);
                } catch (e) {
                  console.error("Failed to copy code", e);
                }
              }

              return (
                <div className="group relative">
                  <pre
                    className={cn(
                      "overflow-auto rounded-lg bg-slate-950/90 p-3 text-xs",
                      className
                    )}
                    {...props}
                  >
                    <code>{children}</code>
                  </pre>
                  <button
                    type="button"
                    onClick={handleCopy}
                    className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-md bg-slate-900/90 px-2 py-1 text-[10px] text-slate-300 opacity-0 shadow-sm ring-1 ring-slate-700 transition-opacity group-hover:opacity-100"
                    title={isCopied ? "Copied" : "Copy"}
                  >
                    {isCopied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                    {isCopied ? "Copied" : "Copy"}
                  </button>
                </div>
              );
            },
          }}
        >
          {text}
        </ReactMarkdown>
      )}

      {images.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {images.map((url, idx) => (
            <button
              type="button"
              key={`${url}-${idx}`}
              className="relative overflow-hidden rounded-lg border border-slate-700 bg-slate-900 hover:border-slate-400"
              onClick={() => {
                const w = window.open();
                if (w) {
                  w.document.write(
                    `<img src="${url}" style="max-width: 100%; max-height: 100vh; object-fit: contain; background: #020617;" />`
                  );
                }
              }}
            >
              <img src={url} alt="attachment" className="h-24 w-24 object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

