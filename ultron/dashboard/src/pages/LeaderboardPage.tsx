import { useState, useEffect } from 'react';
import { api, apiPost } from '../api/client';
import { useLocale } from '../contexts/LocaleContext';
import { formatTemplate } from '../i18n/translations';

export default function LeaderboardPage() {
  const { t } = useLocale();
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    api('/dashboard/leaderboard?limit=30').then(setData).catch(() => {});
  }, []);

  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, any>>({});

  const toggleRow = async (id: string) => {
    if (expandedId === id) { setExpandedId(null); return; }
    setExpandedId(id);
    if (!details[id]) {
      try {
        const j = await apiPost('/memory/details', { memory_ids: [id] });
        const m = j.data?.[0] || null;
        setDetails(prev => ({ ...prev, [id]: m }));
      } catch {
        setDetails(prev => ({ ...prev, [id]: null }));
      }
    }
  };

  const rankCls = (i: number) => i === 0 ? 'bg-gold text-ink' : i === 1 ? 'bg-mid-gray text-ink' : i === 2 ? 'bg-oxide text-bg-page' : 'bg-paper text-muted';
  const tierCls = (t: string) => t === 'hot' ? 'tag-hot' : t === 'warm' ? 'tag-warm' : 'tag-cold';

  const renderCol = (title: string, tier: string, items: any[]) => (
    <div className="card-panel p-5 space-y-3">
      <div>
        <span className={`tag ${tierCls(tier)}`}>{tier.toUpperCase()}</span>
        <h3 className="text-lg font-bold font-serif mt-2">{title}</h3>
        <p className="text-xs text-muted">{t('leaderboard.expandHint')}</p>
      </div>
      {!items?.length ? (
        <div className="text-center text-muted text-sm py-6">{t('leaderboard.noData')}</div>
      ) : (
        <div className="space-y-0 divide-y divide-border">
          {items.map((m: any, i: number) => (
            <div key={m.id}>
              <button
                className="w-full flex items-center gap-3 py-3 px-2 text-left hover:bg-paper rounded transition-colors bg-transparent border-none"
                onClick={() => toggleRow(m.id)}
              >
                <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${rankCls(i)}`}>
                  {i + 1}
                </span>
                <span className="tag tag-type text-xs">{m.memory_type}</span>
                <span className="flex-1 min-w-0 truncate text-sm">{m.summary_l0 || m.id.slice(0, 8)}</span>
                <span className="text-primary text-xs font-semibold flex-shrink-0">{formatTemplate(t('leaderboard.rowHits'), { n: m.hit_count })}</span>
                <span className="text-xs text-mid-gray flex-shrink-0">{expandedId === m.id ? '−' : '+'}</span>
              </button>
              {expandedId === m.id && (
                <div className="pl-10 pb-4 text-sm text-muted space-y-2 animate-slide-up">
                  {!details[m.id] ? (
                    <div className="text-xs text-mid-gray">{t('leaderboard.loading')}</div>
                  ) : (
                    <>
                      <div><span className="kicker">{t('dashboard.kickerL0')}</span><p className="mt-1">{details[m.id].summary_l0 || 'N/A'}</p></div>
                      <div><span className="kicker">{t('dashboard.kickerL1')}</span><p className="mt-1">{details[m.id].overview_l1 || 'N/A'}</p></div>
                      <div>
                        <span className="kicker">{t('dashboard.fullContent')}</span>
                        <pre className="mt-1 p-3 bg-paper rounded text-xs whitespace-pre-wrap break-words max-h-[280px] overflow-y-auto">{details[m.id].content}</pre>
                      </div>
                      {details[m.id].context && <div><span className="kicker">{t('dashboard.context')}</span><p className="mt-1">{details[m.id].context}</p></div>}
                      {details[m.id].resolution && <div><span className="kicker">{t('dashboard.resolution')}</span><p className="mt-1">{details[m.id].resolution}</p></div>}
                      {details[m.id].tags?.length > 0 && (
                        <div className="flex gap-2 flex-wrap">
                          {details[m.id].tags.map((t: string) => <span key={t} className="tag tag-type">{t}</span>)}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );

  if (!data) return <div className="p-6 text-sm text-muted">{t('leaderboard.pageLoading')}</div>;

  return (
    <div className="p-6 space-y-6 max-w-[1200px] mx-auto">
      <div>
        <h1 className="text-3xl font-bold font-serif">{t('leaderboard.title')}</h1>
        <p className="text-sm text-muted mt-2">{t('leaderboard.subtitle')}</p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {renderCol('HOT', 'hot', data.hot)}
        {renderCol('WARM', 'warm', data.warm)}
        {renderCol('COLD', 'cold', data.cold)}
      </div>
    </div>
  );
}
