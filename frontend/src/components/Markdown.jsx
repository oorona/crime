import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Renders the assistant's Markdown reports. react-markdown never renders raw
// HTML, so model output cannot inject markup. Styles live in index.css
// under .md so both the mini chat and the chat page share them.
const components = {
  a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
  table: ({ node, ...props }) => <div className="md-table"><table {...props} /></div>,
};

export default function Markdown({ text, streaming, className = '' }) {
  return (
    <div className={`md ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{text || ''}</ReactMarkdown>
      {streaming && text && <span className="md-caret"> ▍</span>}
    </div>
  );
}
