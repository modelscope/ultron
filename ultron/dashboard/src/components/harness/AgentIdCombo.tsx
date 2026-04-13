import { useState, useRef, useEffect } from 'react';
import { useLocale } from '../../contexts/LocaleContext';

interface Profile { agent_id: string; product: string }

interface Props {
  value: string;
  onChange: (v: string) => void;
  profiles: Profile[];
  placeholder?: string;
  className?: string;
}

export default function AgentIdCombo({ value, onChange, profiles, placeholder, className = '' }: Props) {
  const { t } = useLocale();
  const ph = placeholder ?? t('harness.agentIdPlaceholder');
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const filtered = profiles.filter(p =>
    !value || p.agent_id.toLowerCase().includes(value.toLowerCase())
  );

  return (
    <div ref={ref} className={`relative ${className}`}>
      <input
        placeholder={ph}
        value={value}
        onChange={e => { onChange(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        className="w-full min-w-[260px]"
      />
      {open && filtered.length > 0 && (
        <div className="absolute z-10 left-0 right-0 mt-1 bg-surface border border-border rounded-card-sm shadow-lg max-h-[200px] overflow-y-auto">
          {filtered.map(p => (
            <button
              key={p.agent_id}
              className="w-full text-left px-3 py-2 text-sm hover:bg-warm-gray transition-colors bg-transparent border-none flex items-center justify-between"
              onClick={() => { onChange(p.agent_id); setOpen(false); }}
            >
              <span className="font-mono text-xs truncate">{p.agent_id}</span>
              <span className="text-xs text-muted ml-2 flex-shrink-0">{p.product}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
