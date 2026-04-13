import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';
import { useLocale } from '../contexts/LocaleContext';
import Pagination from '../components/Pagination';
import EmptyState from '../components/EmptyState';

export default function SkillsPage() {
  const { t } = useLocale();
  const [skills, setSkills] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('catalog');
  const [category, setCategory] = useState('');
  const [categories, setCategories] = useState<string[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    api('/dashboard/overview').then(d => {
      const allCats = { ...(d.skills?.internal_categories || {}), ...(d.skills?.catalog_categories || {}) };
      const keys = Object.keys(allCats).filter(Boolean);
      keys.sort((a, b) => a.localeCompare(b));
      setCategories(keys);
    }).catch(() => {});
  }, []);

  const loadSkills = useCallback(async () => {
    try {
      const d = await api(`/dashboard/skills?q=${encodeURIComponent(query)}&source=${source}&category=${encodeURIComponent(category)}&page=${page}&page_size=20`);
      setSkills(d.data || []);
      setTotal(d.total || 0);
    } catch {}
  }, [query, source, category, page]);

  useEffect(() => { loadSkills(); }, [loadSkills]);

  return (
    <div className="p-6 space-y-6 max-w-[1200px] mx-auto">
      <h1 className="text-3xl font-bold font-serif">{t('skills.title')}</h1>

      <section className="panel-surface p-5 space-y-4">
        <div className="flex flex-wrap gap-3 items-center">
          <input
            type="text"
            placeholder={t('skills.searchPlaceholder')}
            value={query}
            onChange={e => { setQuery(e.target.value); setPage(1); }}
            className="flex-1 min-w-[200px]"
          />
          <select value={source} onChange={e => { setSource(e.target.value); setPage(1); }}>
            <option value="">{t('skills.allSources')}</option>
            <option value="internal">{t('skills.internal')}</option>
            <option value="catalog">{t('skills.sourceModelScope')}</option>
          </select>
          <select value={category} onChange={e => { setCategory(e.target.value); setPage(1); }}>
            <option value="">{t('skills.allCategories')}</option>
            {categories.map(c => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        {skills.length === 0 ? (
          <EmptyState title={t('skills.empty')} />
        ) : (
          <div className="space-y-3">
            {skills.map(s => (
              <div
                key={s.id}
                className="record-card bg-surface p-4 cursor-pointer"
                onClick={() => setExpandedId(expandedId === s.id ? null : s.id)}
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`tag ${s.source === 'internal' ? 'tag-internal' : 'tag-source'}`}>
                    {s.source === 'internal' ? t('skills.internal') : t('skills.sourceModelScope')}
                  </span>
                  {(s.categories || []).map((c: string) => (
                    <span key={c} className="tag tag-type">
                      {c}
                    </span>
                  ))}
                  <span className="flex-1 min-w-0 truncate text-sm font-semibold">{s.name}</span>
                  {s.source === 'catalog' && (
                    <a
                      href={`https://modelscope.cn/skills/${String(s.id).replace(/^\/+/, '')}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-primary text-xs px-2 py-1 no-underline"
                      onClick={e => e.stopPropagation()}
                    >
                      {t('skills.openModelScope')}
                    </a>
                  )}
                </div>
                {expandedId === s.id && (
                  <div className="mt-4 pt-4 border-t border-border text-sm text-muted animate-slide-up">
                    <p>{s.description || t('skills.noDescription')}</p>
                    <p className="text-xs text-mid-gray mt-2">{t('skills.idLabel')}: {s.id}</p>
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
