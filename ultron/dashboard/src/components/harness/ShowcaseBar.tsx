import { useState } from 'react';
import { api } from '../../api/client';
import { useLocale } from '../../contexts/LocaleContext';

interface ShowcaseDetail {
  slug: string;
  name: string;
  description: string;
  emoji: string;
  short_code: string;
  tags: string[];
  body: string;
}

export default function ShowcaseModal() {
  const { t, locale } = useLocale();
  const [detail, setDetail] = useState<ShowcaseDetail | null>(null);

  const open = async () => {
    try {
      const d = await api(`/harness/showcase/financebot?lang=${locale}`);
      if (d.success) setDetail(d.data);
    } catch {}
  };

  return (
    <>
      <button
        type="button"
        className="inline-flex items-center text-xs text-accent hover:underline cursor-pointer bg-transparent border-none p-0"
        onClick={open}
      >
        {t('harness.showcase.clickExample')}
      </button>

      {detail && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(0,0,0,0.5)]"
          onClick={e => { if (e.target === e.currentTarget) setDetail(null); }}
        >
          <div className="bg-surface rounded-card w-full max-w-[800px] max-h-[80vh] overflow-hidden mx-4 shadow-xl">
            <div className="overflow-y-auto max-h-[80vh] p-6 space-y-5">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <span className="text-4xl">{detail.emoji}</span>
                <div>
                  <h2 className="text-xl font-bold">{detail.name}</h2>
                  <p className="text-sm text-muted italic">{detail.description}</p>
                </div>
              </div>
              <button
                type="button"
                className="text-muted hover:text-ink text-2xl bg-transparent border-none cursor-pointer leading-none"
                onClick={() => setDetail(null)}
              >&times;</button>
            </div>

            <div className="flex flex-wrap gap-1.5">
              {detail.tags.map(tag => (
                <span key={tag} className="text-xs px-2 py-0.5 rounded-full bg-warm-gray text-muted">{tag}</span>
              ))}
            </div>

            <ShowcaseBody body={detail.body} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function ShowcaseBody({ body }: { body: string }) {
  const sections = parseMarkdownSections(body);
  return (
    <div className="space-y-4">
      {sections.map((sec, i) => (
        <div key={i}>
          {sec.heading && <h3 className="text-base font-semibold mb-2">{sec.heading}</h3>}
          {sec.blocks.map((block, j) => (
            <div key={j}>
              {block.type === 'quote' && !block.text.includes('短码') && !block.text.toLowerCase().includes('short code') && (
                <blockquote className="border-l-3 border-accent pl-3 text-sm italic text-muted my-2" dangerouslySetInnerHTML={{ __html: renderInline(block.text) }} />
              )}
              {block.type === 'list' && (
                <ul className="space-y-1 my-2 ml-4">
                  {block.items!.map((item, k) => (
                    <li key={k} className="text-sm list-disc" dangerouslySetInnerHTML={{ __html: renderInline(item) }} />
                  ))}
                </ul>
              )}
              {block.type === 'table' && (
                <div className="overflow-x-auto my-3">
                  <table className="w-full text-xs border-collapse">
                    <thead>
                      <tr>{block.headers!.map((h, k) => (
                        <th key={k} className="text-left border border-border bg-warm-gray px-3 py-2 font-semibold" dangerouslySetInnerHTML={{ __html: renderInline(h) }} />
                      ))}</tr>
                    </thead>
                    <tbody>
                      {block.rows!.map((row, k) => (
                        <tr key={k} className="hover:bg-warm-gray transition-colors">
                          {row.map((cell, l) => (
                            <td key={l} className="border border-border px-3 py-2" dangerouslySetInnerHTML={{ __html: renderInline(cell) }} />
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {block.type === 'code' && (
                <pre className="bg-[rgba(0,0,0,0.03)] rounded p-3 text-xs overflow-x-auto my-2 font-mono whitespace-pre-wrap">{block.text}</pre>
              )}
              {block.type === 'paragraph' && block.text.trim() && !block.text.startsWith('*Powered by') && (
                <p className="text-sm my-1.5 leading-relaxed" dangerouslySetInnerHTML={{ __html: renderInline(block.text) }} />
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

interface Block { type: string; text: string; items?: string[]; headers?: string[]; rows?: string[][]; src?: string; alt?: string }
interface Section { heading: string; blocks: Block[] }

function parseMarkdownSections(md: string): Section[] {
  const lines = md.split('\n');
  const sections: Section[] = [];
  let cur: Section = { heading: '', blocks: [] };
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^#{2,3}\s/.test(line)) {
      if (cur.heading || cur.blocks.length) sections.push(cur);
      cur = { heading: line.replace(/^#{2,3}\s+/, ''), blocks: [] };
      i++; continue;
    }
    if (/^<(p |\/p|br|sub|\/sub|img )/.test(line.trim())) {
      const m = line.match(/src="([^"]+)".*?alt="([^"]*)"/);
      if (m) cur.blocks.push({ type: 'image', text: '', src: m[1], alt: m[2] });
      i++; continue;
    }
    if (line.startsWith('```')) {
      const cl: string[] = []; i++;
      while (i < lines.length && !lines[i].startsWith('```')) { cl.push(lines[i]); i++; }
      cur.blocks.push({ type: 'code', text: cl.join('\n') }); i++; continue;
    }
    if (line.includes('|') && line.trim().startsWith('|')) {
      const tl: string[] = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim().startsWith('|')) { tl.push(lines[i]); i++; }
      if (tl.length >= 2) {
        const pr = (r: string) => r.split('|').slice(1, -1).map(c => c.trim());
        const ds = tl[1].includes('---') ? 2 : 1;
        cur.blocks.push({ type: 'table', text: '', headers: pr(tl[0]), rows: tl.slice(ds).map(pr) });
      }
      continue;
    }
    if (line.startsWith('>')) {
      const ql: string[] = [];
      while (i < lines.length && lines[i].startsWith('>')) { ql.push(lines[i].replace(/^>\s?/, '')); i++; }
      cur.blocks.push({ type: 'quote', text: ql.join(' ') }); continue;
    }
    if (line.startsWith('- ')) {
      const items: string[] = [];
      while (i < lines.length && lines[i].startsWith('- ')) { items.push(lines[i].slice(2)); i++; }
      cur.blocks.push({ type: 'list', text: '', items }); continue;
    }
    if (line.trim() === '---' || line.trim() === '***') { i++; continue; }
    if (!line.trim()) { i++; continue; }
    cur.blocks.push({ type: 'paragraph', text: line }); i++;
  }
  if (cur.heading || cur.blocks.length) sections.push(cur);
  return sections;
}

function renderInline(text: string): string {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code class="text-xs bg-warm-gray px-1 py-0.5 rounded font-mono">$1</code>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="text-accent underline">$1</a>');
}
