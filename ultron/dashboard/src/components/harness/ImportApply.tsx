import { useState } from 'react';
import { useLocale } from '../../contexts/LocaleContext';
import HarnessIoBlurb from './HarnessIoBlurb';

const PRODUCTS = ['nanobot', 'openclaw', 'hermes'];

export default function ImportApply({ onImported }: { onImported?: () => void }) {
  const { t } = useLocale();
  const [code, setCode] = useState('');
  const [product, setProduct] = useState('nanobot');
  const [curlCmd, setCurlCmd] = useState('');

  const generate = () => {
    const trimmed = code.trim();
    if (!trimmed) return;
    if (!confirm(t('harness.import.warnOverwrite'))) return;
    const base = location.origin;
    const cmd = `curl -sL "${base}/i/${trimmed}?product=${product}" | bash`;
    setCurlCmd(cmd);
    onImported?.();
  };

  const copy = async (el: HTMLButtonElement) => {
    try {
      await navigator.clipboard.writeText(curlCmd);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = curlCmd;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    const prev = el.textContent;
    el.textContent = t('harness.copied');
    setTimeout(() => { el.textContent = prev; }, 1500);
  };

  return (
    <div className="card-panel p-5 space-y-4">
      <div>
        <span className="kicker">{t('harness.import.kicker')}</span>
        <HarnessIoBlurb inputKey="harness.import.input" outputKey="harness.import.output" />
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <input
          placeholder={t('harness.import.shareCode')}
          value={code}
          onChange={e => setCode(e.target.value)}
          className="min-w-[180px]"
        />
        <label className="flex items-center gap-1 text-sm text-muted">
          <span>{t('harness.import.importTo')}</span>
          <select value={product} onChange={e => setProduct(e.target.value)}>
            {PRODUCTS.map(p => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
        <button type="button" className="btn-primary text-sm" onClick={generate}>
          {t('harness.import.import')}
        </button>
      </div>
      {curlCmd && (
        <div className="space-y-2 animate-slide-up">
          <p className="text-sm text-muted">
            {t('harness.import.runInTerminal')}
          </p>
          <div className="flex items-center gap-2 bg-paper rounded-card-sm p-3">
            <code className="text-xs font-mono flex-1 break-all select-all">
              {curlCmd}
            </code>
            <button
              type="button"
              className="btn-outline text-xs flex-shrink-0"
              onClick={e => copy(e.currentTarget)}
            >
              {t('harness.copy')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
