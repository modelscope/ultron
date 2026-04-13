import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useLocale } from '../contexts/LocaleContext';
import { formatTemplate } from '../i18n/translations';
import MetricCard from '../components/MetricCard';
import Pagination from '../components/Pagination';
import EmptyState from '../components/EmptyState';

function esc(s: string) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

export default function DashboardPage() {
  const { t } = useLocale();
  const [stats, setStats] = useState<any>(null);
  const [memories, setMemories] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState('');
  const [memType, setMemType] = useState('');
  const [tier, setTier] = useState('');
  const [sort, setSort] = useState('hit_count');
  const [types, setTypes] = useState<string[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    api('/dashboard/overview').then(d => {
      setStats(d);
      const t = Object.keys(d.memory?.by_type || {});
      setTypes(t);
      if (t.includes('life')) setMemType('life');
    }).catch(() => {});
  }, []);

  const loadMemories = useCallback(async () => {
    try {
      const d = await api(`/dashboard/memories?q=${encodeURIComponent(query)}&memory_type=${memType}&tier=${tier}&sort=${sort}&page=${page}&page_size=20`);
      setMemories(d.data || []);
      setTotal(d.total || 0);
    } catch {}
  }, [query, memType, tier, sort, page]);

  useEffect(() => { loadMemories(); }, [loadMemories]);

  const tierCls = (t: string) => t === 'hot' ? 'tag-hot' : t === 'warm' ? 'tag-warm' : 'tag-cold';

  return (
    <div className="p-6 space-y-6 max-w-[1200px] mx-auto">
      <h1 className="text-3xl font-bold font-serif">{t('dashboard.title')}</h1>

      {stats && (
        <section className="panel-surface">
          <div className="metrics-row">
            <MetricCard label={t('dashboard.totalMemories')} value={(stats.memory?.total || 0).toLocaleString()} />
            <MetricCard label="HOT" value={(stats.memory?.by_tier?.hot || 0).toLocaleString()} hint={t('dashboard.hotHint')} />
            <MetricCard label="WARM" value={(stats.memory?.by_tier?.warm || 0).toLocaleString()} hint={t('dashboard.warmHint')} />
            <MetricCard label="COLD" value={(stats.memory?.by_tier?.cold || 0).toLocaleString()} hint={t('dashboard.coldHint')} />
            <MetricCard label={t('dashboard.internalSkills')} value={(stats.skills?.internal || 0).toLocaleString()} />
            <MetricCard label={t('dashboard.catalogSkills')} value={(stats.skills?.catalog || 0).toLocaleString()} />
          </div>
        </section>
      )}

      <section className="panel-surface p-5 space-y-4">
        <div className="flex flex-wrap gap-3 items-center">
          <input
            type="text"
            placeholder={t('dashboard.searchPlaceholder')}
            value={query}
            onChange={e => { setQuery(e.target.value); setPage(1); }}
            className="flex-1 min-w-[200px]"
          />
          <select value={memType} onChange={e => { setMemType(e.target.value); setPage(1); }}>
            <option value="">{t('dashboard.allTypes')}</option>
            {types.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <select value={tier} onChange={e => { setTier(e.target.value); setPage(1); }}>
            <option value="">{t('dashboard.allTiers')}</option>
            <option value="hot">HOT</option>
            <option value="warm">WARM</option>
            <option value="cold">COLD</option>
          </select>
          <select value={sort} onChange={e => { setSort(e.target.value); setPage(1); }}>
            <option value="hit_count">{t('dashboard.byHits')}</option>
            <option value="created_at">{t('dashboard.byDate')}</option>
          </select>
        </div>

        {memories.length === 0 ? (
          <EmptyState title={t('dashboard.empty')} />
        ) : (
          <div className="space-y-3">
            {memories.map(m => (
              <div
                key={m.id}
                className="record-card bg-surface p-4 cursor-pointer"
                onClick={() => setExpandedId(expandedId === m.id ? null : m.id)}
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`tag ${tierCls(m.tier)}`}>{m.tier.toUpperCase()}</span>
                  <span className="tag tag-type">{m.memory_type}</span>
                  <span className="tag tag-hot text-xs">{formatTemplate(t('dashboard.hits'), { n: m.hit_count })}</span>
                  <span className="flex-1 min-w-0 truncate text-sm">{m.summary_l0 || m.content?.slice(0, 100)}</span>
                </div>
                {expandedId === m.id && (
                  <div className="mt-4 pt-4 border-t border-border text-sm text-muted space-y-3 animate-slide-up">
                    <div><span className="kicker">{t('dashboard.kickerL0')}</span><p className="mt-1">{m.summary_l0 || 'N/A'}</p></div>
                    <div><span className="kicker">{t('dashboard.kickerL1')}</span><p className="mt-1">{m.overview_l1 || 'N/A'}</p></div>
                    <div>
                      <span className="kicker">{t('dashboard.fullContent')}</span>
                      <pre className="mt-1 p-3 bg-paper rounded-card-sm text-xs whitespace-pre-wrap break-words max-h-[300px] overflow-y-auto">{m.content}</pre>
                    </div>
                    {m.context && <div><span className="kicker">{t('dashboard.context')}</span><p className="mt-1">{m.context}</p></div>}
                    {m.resolution && <div><span className="kicker">{t('dashboard.resolution')}</span><p className="mt-1">{m.resolution}</p></div>}
                    {m.tags?.length > 0 && (
                      <div className="flex gap-2 flex-wrap">
                        {m.tags.map((t: string) => <span key={t} className="tag tag-type">{esc(t)}</span>)}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        <Pagination page={page} total={total} pageSize={20} onChange={setPage} />
      </section>
    </div>
  );
}
