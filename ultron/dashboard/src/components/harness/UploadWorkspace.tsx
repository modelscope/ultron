import { useState, useRef } from 'react';
import { apiPost } from '../../api/client';
import { useLocale } from '../../contexts/LocaleContext';
import { formatTemplate } from '../../i18n/translations';
import HarnessIoBlurb from './HarnessIoBlurb';

const PRODUCT_ALLOWLISTS: Record<string, string[]> = {
  nanobot: [
    'AGENTS.md', 'SOUL.md', 'USER.md', 'TOOLS.md', 'HEARTBEAT.md',
    'memory/MEMORY.md', 'memory/HISTORY.md',
    'skills/*/SKILL.md', 'skills/*/_meta.json', 'skills/*/scripts/*',
    'skills/*/setup.md', 'skills/*/operations.md', 'skills/*/boundaries.md',
  ],
  openclaw: [
    'AGENTS.md', 'SOUL.md', 'USER.md', 'TOOLS.md', 'HEARTBEAT.md',
    'IDENTITY.md', 'BOOTSTRAP.md', 'MEMORY.md',
    'memory/*.md', 'memory/*.json',
    'skills/*/SKILL.md', 'skills/*/_meta.json', 'skills/*/scripts/*',
  ],
  hermes: [
    'SOUL.md', 'memories/*.md',
    'skills/*/SKILL.md', 'skills/*/DESCRIPTION.md', 'skills/*/_meta.json', 'skills/*/scripts/*', 'skills/*/references/*',
    'skills/*/*/SKILL.md', 'skills/*/*/_meta.json', 'skills/*/*/scripts/*', 'skills/*/*/references/*',
  ],
};

const PRODUCT_DIRS: Record<string, string> = { nanobot: '.nanobot', openclaw: '.openclaw', hermes: '.hermes' };
const PRODUCT_MARKERS: Record<string, string> = { '.nanobot': 'nanobot', '.openclaw': 'openclaw', '.hermes': 'hermes' };

function globMatch(pattern: string, path: string) {
  const re = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '[^/]*');
  return new RegExp('^' + re + '$').test(path);
}

function matchesAllowlist(relPath: string, product: string) {
  const pats = PRODUCT_ALLOWLISTS[product];
  if (!pats) return false;
  return pats.some(p => globMatch(p, relPath));
}

function resolveWorkspaceRelPath(fullRelPath: string, product: string) {
  const parts = fullRelPath.split('/');
  const marker = PRODUCT_DIRS[product];
  if (!marker) return null;
  const markerIdx = parts.indexOf(marker);
  if (markerIdx < 0) return null;
  if (product === 'hermes') return parts.slice(markerIdx + 1).join('/') || null;
  const wsIdx = parts.indexOf('workspace', markerIdx + 1);
  if (wsIdx >= 0) return parts.slice(wsIdx + 1).join('/') || null;
  return parts.slice(markerIdx + 1).join('/') || null;
}

function detectProduct(fileList: FileList | File[]) {
  for (const file of fileList) {
    const rel = (file as any).webkitRelativePath || file.name;
    for (const part of rel.split('/')) {
      if (PRODUCT_MARKERS[part]) return PRODUCT_MARKERS[part];
    }
  }
  return null;
}

function formatSize(bytes: number) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function createAgentId() {
  const c = globalThis.crypto;
  if (c?.randomUUID) return c.randomUUID();
  if (c?.getRandomValues) {
    const bytes = new Uint8Array(16);
    c.getRandomValues(bytes);
    // RFC 4122 v4 bits
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0'));
    return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10, 16).join('')}`;
  }
  // Last-resort fallback for very old runtimes.
  return `ag-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export default function UploadWorkspace({ onUploaded }: { onUploaded?: () => void }) {
  const { t } = useLocale();
  const [lastAgentId, setLastAgentId] = useState('');
  const [product, setProduct] = useState('');
  const [files, setFiles] = useState<Map<string, { file: File }>>(new Map());
  const [skipped, setSkipped] = useState(0);
  const [status, setStatus] = useState('');
  const [statusCls, setStatusCls] = useState('');
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const processFiles = (fileList: FileList | File[]) => {
    const det = detectProduct(fileList);
    if (!det) { alert(t('harness.upload.alertUnrecognized')); return; }
    setProduct(det);
    const newFiles = new Map<string, { file: File }>();
    let skip = 0;
    for (const file of fileList) {
      if (file.size > 1024 * 1024) { skip++; continue; }
      if (file.name.startsWith('.')) { skip++; continue; }
      const fullRel = (file as any).webkitRelativePath || file.name;
      if (fullRel.split('/').some((p: string) => p.startsWith('.') && !Object.keys(PRODUCT_MARKERS).includes(p))) { skip++; continue; }
      const relPath = resolveWorkspaceRelPath(fullRel, det);
      if (!relPath) { skip++; continue; }
      if (!matchesAllowlist(relPath, det)) { skip++; continue; }
      newFiles.set(relPath, { file });
    }
    setFiles(newFiles);
    setSkipped(skip);
    setStatus(''); setProgress(0);
  };

  const upload = async () => {
    if (!product || files.size === 0) { alert(t('harness.upload.alertNoFiles')); return; }
    const agentId = createAgentId();
    setBusy(true); setStatus(t('harness.upload.reading')); setStatusCls(''); setProgress(10);
    const resources: Record<string, string> = {};
    let i = 0;
    for (const [rel, info] of files) {
      try { resources[rel] = await info.file.text(); } catch {}
      i++;
      setProgress(10 + Math.round((i / files.size) * 40));
    }
    setStatus(formatTemplate(t('harness.upload.uploading'), { n: Object.keys(resources).length })); setProgress(60);
    try {
      const d = await apiPost('/harness/sync/up', { agent_id: agentId, product, resources });
      setProgress(100);
      if (d.success) {
        setLastAgentId(agentId);
        setStatus(formatTemplate(t('harness.upload.uploadComplete'), {
          files: files.size,
          rev: d.data?.revision ?? '?',
        }));
        setStatusCls('text-accent');
        setFiles(new Map()); setSkipped(0);
        onUploaded?.();
      } else {
        setStatus(d.detail || t('harness.upload.uploadFailed')); setStatusCls('text-danger'); setProgress(0);
      }
    } catch { setStatus(t('harness.upload.uploadFailed')); setStatusCls('text-danger'); setProgress(0); }
    setBusy(false);
  };

  const clear = () => { setFiles(new Map()); setSkipped(0); setProduct(''); setStatus(''); setProgress(0); };
  const totalSize = Array.from(files.values()).reduce((s, f) => s + f.file.size, 0);

  return (
    <div className="card-panel p-5 space-y-4">
      <div>
        <span className="kicker">{t('harness.upload.kicker')}</span>
        <HarnessIoBlurb inputKey="harness.upload.input" outputKey="harness.upload.output" />
      </div>
      {files.size === 0 && (
      <div
        className="border-2 border-dashed border-border rounded-card-sm p-7 text-center cursor-pointer hover:border-primary transition-colors relative"
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          {...{ webkitdirectory: '', directory: '', multiple: true } as any}
          onChange={e => { if (e.target.files) processFiles(e.target.files); e.target.value = ''; }}
        />
        <div className="text-2xl text-muted mb-1">&#128193;</div>
        <div className="text-sm text-muted"><strong className="text-ink">{t('harness.upload.clickSelect')}</strong></div>
        <div className="text-xs text-mid-gray mt-1">
          {t('harness.upload.hintPaths')}{' '}
          <code className="text-primary">~/.nanobot</code>, <code className="text-primary">~/.openclaw</code>,{' '}
          <code className="text-primary">~/.hermes</code>
        </div>
      </div>
      )}

      {files.size > 0 && (
        <div className="space-y-3 animate-slide-up">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted">
              {t('harness.upload.selected')} <strong className="text-ink">{files.size}</strong> {t('harness.upload.files')} (
              <strong className="text-ink">{formatSize(totalSize)}</strong>)
            </span>
            <button className="btn-outline text-xs" onClick={clear}>{t('harness.upload.clearAll')}</button>
          </div>
          {skipped > 0 && (
            <p className="text-xs text-mid-gray">{formatTemplate(t('harness.upload.skipped'), { n: skipped })}</p>
          )}
          <div className="bg-paper rounded-card-sm p-2 max-h-[200px] overflow-y-auto font-mono text-xs divide-y divide-border">
            {Array.from(files.entries()).map(([rel, info]) => (
              <div key={rel} className="flex items-center justify-between py-1 px-2">
                <span className="flex-1 min-w-0 truncate">{rel}</span>
                <span className="text-muted flex-shrink-0 ml-3">{formatSize(info.file.size)}</span>
                <button className="text-danger ml-2 bg-transparent border-none text-sm" onClick={() => { const n = new Map(files); n.delete(rel); setFiles(n); }}>×</button>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-3">
            <button className="btn-primary text-sm" onClick={upload} disabled={busy}>{t('harness.upload.uploadToServer')}</button>
            {progress > 0 && (
              <div className="flex-1 h-1 bg-paper rounded overflow-hidden">
                <div className="h-full bg-accent rounded transition-all" style={{ width: `${progress}%` }} />
              </div>
            )}
          </div>
        </div>
      )}
      {status && <p className={`text-sm ${statusCls || 'text-muted'}`}>{status}</p>}
      {lastAgentId && (
        <div className="bg-paper rounded-card-sm p-3 flex items-center gap-3">
          <span className="text-xs text-muted">{t('harness.upload.agentId')}:</span>
          <code className="text-xs text-accent flex-1 break-all">{lastAgentId}</code>
          <button type="button" className="btn-outline text-xs flex-shrink-0" onClick={() => navigator.clipboard.writeText(lastAgentId)}>{t('harness.copy')}</button>
        </div>
      )}
    </div>
  );
}
