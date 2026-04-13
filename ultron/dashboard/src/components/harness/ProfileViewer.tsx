import { useState } from 'react';
import { api, apiDelete } from '../../api/client';
import { useLocale } from '../../contexts/LocaleContext';
import AgentIdCombo from './AgentIdCombo';
import HarnessIoBlurb from './HarnessIoBlurb';

interface Profile { agent_id: string; product: string }

export default function ProfileViewer({
  profiles,
  onDeleted,
}: {
  profiles: Profile[];
  onDeleted?: () => void;
}) {
  const { t } = useLocale();
  const [agentId, setAgentId] = useState('');
  const [profile, setProfile] = useState<any>(null);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = async () => {
    if (!agentId) return;
    try {
      const d = await api(`/harness/profile?agent_id=${encodeURIComponent(agentId)}`);
      setProfile(d.data);
    } catch { setProfile(null); }
  };

  const removeAgent = async () => {
    if (!profile?.agent_id && !agentId) return;
    const id = profile?.agent_id ?? agentId;
    if (!confirm(t('harness.profile.confirmDeleteAgent'))) return;
    setDeleting(true);
    try {
      const d = await apiDelete('/harness/agents', { agent_id: id });
      if (d.success) {
        setProfile(null);
        setExpandedIdx(null);
        onDeleted?.();
      } else {
        alert(d.detail || t('harness.profile.deleteFailed'));
      }
    } catch {
      alert(t('harness.profile.deleteFailed'));
    } finally {
      setDeleting(false);
    }
  };

  const resources = profile?.resources || {};
  const files = Object.keys(resources);

  return (
    <div className="card-panel p-5 space-y-4">
      <div>
        <span className="kicker">{t('harness.profile.kicker')}</span>
        <HarnessIoBlurb inputKey="harness.profile.input" outputKey="harness.profile.output" />
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <AgentIdCombo value={agentId} onChange={setAgentId} profiles={profiles} />
        <button type="button" className="btn-primary text-sm" onClick={load}>{t('harness.profile.loadProfile')}</button>
      </div>
      {profile && (
        <div className="space-y-3 animate-slide-up">
          <div className="flex flex-wrap gap-2 items-center">
            <button
              type="button"
              className="btn-danger text-sm"
              onClick={removeAgent}
              disabled={deleting}
            >
              {t('harness.profile.deleteAgent')}
            </button>
          </div>
          <div className="flex flex-wrap gap-4 text-sm text-muted">
            <span>{t('harness.profile.product')}: <strong className="text-ink">{profile.product || 'nanobot'}</strong></span>
            <span>{t('harness.profile.revision')}: <strong className="text-ink">{profile.revision || 1}</strong></span>
            <span>{t('harness.profile.updated')}: <strong className="text-ink">{profile.updated_at || 'N/A'}</strong></span>
            <span>{t('harness.profile.files')}: <strong className="text-ink">{files.length}</strong></span>
          </div>
          {files.length > 0 && (
            <div className="bg-paper rounded-card-sm p-3 max-h-[400px] overflow-y-auto space-y-1">
              {files.map((f, i) => (
                <div key={f}>
                  <button
                    className="w-full text-left text-sm py-1 px-2 rounded hover:bg-warm-gray transition-colors bg-transparent border-none flex items-center gap-2"
                    onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                  >
                    <span className="text-muted">&#x1F4C4;</span> {f}
                  </button>
                  {expandedIdx === i && (
                    <pre className="ml-6 mt-1 mb-2 p-3 bg-surface border border-border rounded text-xs whitespace-pre-wrap break-all max-h-[200px] overflow-y-auto animate-slide-up">
                      {resources[f]}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
