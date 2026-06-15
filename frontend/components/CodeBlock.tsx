"use client";

import { useEffect, useRef } from "react";
import hljs from "highlight.js/lib/core";
import ini from "highlight.js/lib/languages/ini";
import json from "highlight.js/lib/languages/json";
import markdown from "highlight.js/lib/languages/markdown";
import plaintext from "highlight.js/lib/languages/plaintext";
import xml from "highlight.js/lib/languages/xml";

hljs.registerLanguage("ini", ini);
hljs.registerLanguage("json", json);
hljs.registerLanguage("markdown", markdown);
hljs.registerLanguage("plaintext", plaintext);
hljs.registerLanguage("xml", xml);

function languageForFilename(filename: string): string {
  if (filename.endsWith(".json")) return "json";
  if (filename.endsWith(".conf")) return "ini";
  if (filename.endsWith(".xml") || filename.endsWith(".meta")) return "xml";
  if (filename.endsWith(".md")) return "markdown";
  return "plaintext";
}

export function CodeBlock({ filename, content }: { filename: string; content: string }) {
  const codeRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!codeRef.current) return;
    delete codeRef.current.dataset.highlighted;
    hljs.highlightElement(codeRef.current);
  }, [content]);

  return (
    <pre className="overflow-auto rounded-lg border border-zinc-800 bg-zinc-900 p-4 text-sm leading-relaxed">
      <code ref={codeRef} className={`language-${languageForFilename(filename)} font-mono`}>
        {content}
      </code>
    </pre>
  );
}
