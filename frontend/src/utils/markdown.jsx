
const parseBold = (text) => {
  if (typeof text !== 'string') return text;
  const parts = text.split(/(\*\*.*?\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
};

export const formatMarkdownLite = (rawText) => {
  if (!rawText) return null;
  const text = String(rawText);
  const lines = text.split('\n');
  return lines.map((line, i) => {
    const trimmed = line.trim();
    
    // Handle Checkboxes
    if (trimmed.startsWith('- [ ] ')) {
      return (
        <div key={i} className="md-checkbox">
          <input type="checkbox" readOnly checked={false} />
          <span>{parseBold(trimmed.substring(6))}</span>
        </div>
      );
    }
    if (trimmed.startsWith('- [x] ') || trimmed.startsWith('- [X] ')) {
      return (
        <div key={i} className="md-checkbox checked">
          <input type="checkbox" readOnly checked={true} />
          <span style={{ textDecoration: 'line-through', opacity: 0.6 }}>{parseBold(trimmed.substring(6))}</span>
        </div>
      );
    }

    // Handle Headers
    if (trimmed.startsWith('# ')) return <h1 key={i}>{parseBold(trimmed.substring(2))}</h1>;
    if (trimmed.startsWith('## ')) return <h2 key={i}>{parseBold(trimmed.substring(3))}</h2>;
    if (trimmed.startsWith('### ')) return <h3 key={i}>{parseBold(trimmed.substring(4))}</h3>;

    // Handle Bullet Lists
    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      return <li key={i} className="md-li">{parseBold(trimmed.substring(2))}</li>;
    }

    // Handle Numbered Lists
    if (/^\d+\.\s/.test(trimmed)) {
      const dotIndex = trimmed.indexOf('.');
      return <li key={i} className="md-li-num">{parseBold(trimmed.substring(dotIndex + 1).trim())}</li>;
    }
    
    // Handle Bold / Normal Paragraph
    if (!trimmed) return <br key={i} />;
    return <p key={i} className="md-p">{parseBold(line)}</p>;
  });
};
