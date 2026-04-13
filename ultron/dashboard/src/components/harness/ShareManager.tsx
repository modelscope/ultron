import { useState, useEffect } from 'react';
import { api, apiPost, apiDelete } from '../../api/client';
import { useLocale } from '../../contexts/LocaleContext';
import AgentIdCombo from './AgentIdCombo';
import HarnessIoBlurb from './HarnessIoBlurb';

interface Profile { agent_id: string; product: string }

async function copyText(text: string) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {}

  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

export default function ShareManager({ profiles }: { profiles: Profile[] }) {
  const { t } = useLocale();
  const [shares, setShares] = useState<any[]>([]);
  const [agentId, setAgentId] = useState('');

  const load = async () => {
    try {
      const d = await api('/harness/shares');
      setShares(d.data || []);
    } catch {}
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!agentId) return;
    await apiPost('/harness/share', { agent_id: agentId, visibility: 'public' });
    load();
  };

  const remove = async (token: string) => {
    if (!confirm(t('harness.share.confirmDelete'))) return;
    await apiDelete('/harness/share', { token });
    load();
  };

  const copyCode = async (code: string, el: HTMLElement) => {
    const ok = await copyText(code);
    const prev = el.textContent;
    el.textContent = ok ? t('harness.copied') : code;
    setTimeout(() => { el.textContent = prev || code; }, 1500);
  };

  return (
    <div className="card-panel p-5 space-y-4">
      <div>
        <span className="kicker">{t('harness.share.kicker')}</span>
        <HarnessIoBlurb inputKey="harness.share.input" outputKey="harness.share.output" />
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <AgentIdCombo value={agentId} onChange={setAgentId} profiles={profiles} />
        <button type="button" className="btn-primary text-sm" onClick={create}>{t('harness.share.createShare')}</button>
      </div>
      {shares.length === 0 ? (
        <p className="text-sm text-muted">{t('harness.share.noShares')}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="py-2 px-3 text-xs text-muted font-semibold">{t('harness.share.colCode')}</th>
                <th className="py-2 px-3 text-xs text-muted font-semibold">{t('harness.share.colAgent')}</th>
                <th className="py-2 px-3 text-xs text-muted font-semibold">{t('harness.share.colCreated')}</th>
                <th className="py-2 px-3"></th>
              </tr>
            </thead>
            <tbody>
              {shares.map(s => (
                <tr key={s.token} className="border-b border-paper">
                  <td className="py-2 px-3">
                    <button
                      type="button"
                      className="font-mono text-xs text-accent bg-paper px-1.5 py-0.5 rounded cursor-pointer hover:opacity-80 border-0"
                      onClick={e => copyCode(s.short_code || s.token.slice(0, 8), e.currentTarget)}
                      title={t('harness.share.copyTitle')}
                    >
                      {s.short_code || s.token.slice(0, 8)}
                    </button>
                  </td>
                  <td className="py-2 px-3 text-muted">{s.source_agent_id || s.sourceDeviceId || '-'}</td>
                  <td className="py-2 px-3 text-muted">{s.created_at || '-'}</td>
                  <td className="py-2 px-3">
                    <button type="button" className="btn-danger text-xs" onClick={() => remove(s.token)}>{t('harness.share.delete')}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
