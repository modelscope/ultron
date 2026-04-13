import { useState, useEffect } from 'react';
import { api, apiPost } from '../../api/client';
import { useLocale } from '../../contexts/LocaleContext';
import { formatTemplate } from '../../i18n/translations';
import AgentIdCombo from './AgentIdCombo';
import HarnessIoBlurb from './HarnessIoBlurb';

interface Profile { agent_id: string; product: string }
interface StagedMemory { summary: string; content: string; context: string; resolution: string; type: string; tier: string; tags: string[] }
interface StagedSkill {
  name: string;
  description: string;
  source: string;
  sourceType: string;
  fullName: string;
  categories: string[];
}
interface RolePreset { id: string; name: string; description: string; emoji: string }
interface RoleCategory { id: string; label: string; presets: RolePreset[] }

const PERSONALITY_CATEGORIES = new Set(['mbti', 'zodiac']);

export default function ComposeWorkspace({ profiles }: { profiles: Profile[] }) {
  const { t } = useLocale();
  const [agentId, setAgentId] = useState('');
  const [memQuery, setMemQuery] = useState('');
  const [skillQuery, setSkillQuery] = useState('');
  const [memResults, setMemResults] = useState<any[]>([]);
  const [skillResults, setSkillResults] = useState<any[]>([]);
  const [stagedMem, setStagedMem] = useState<Map<string, StagedMemory>>(new Map());
  const [stagedSkill, setStagedSkill] = useState<Map<string, StagedSkill>>(new Map());
  const [status, setStatus] = useState('');
  const [statusCls, setStatusCls] = useState('');
  const [busy, setBusy] = useState(false);

  // Roles state
  const [roleCategories, setRoleCategories] = useState<RoleCategory[]>([]);
  const [roleCatFilter, setRoleCatFilter] = useState('');
  // Independent single-select per group: role (non-personality), mbti, zodiac
  const [selectedRole, setSelectedRole] = useState<RolePreset | null>(null);
  const [selectedRoleCat, setSelectedRoleCat] = useState('');
  const [selectedMbti, setSelectedMbti] = useState<RolePreset | null>(null);
  const [selectedZodiac, setSelectedZodiac] = useState<RolePreset | null>(null);

  useEffect(() => {
    api('/harness/soul-presets')
      .then(d => { if (d.success) setRoleCategories(d.data.categories || []); })
      .catch(() => {});
  }, []);

  const searchMem = async () => {
    if (!memQuery.trim()) return;
    try {
      const d = await api(`/dashboard/memories?q=${encodeURIComponent(memQuery)}&page=1&page_size=20`);
      setMemResults(d.data || []);
    } catch {}
  };

  const searchSkill = async () => {
    if (!skillQuery.trim()) return;
    try {
      const d = await api(`/dashboard/skills?q=${encodeURIComponent(skillQuery)}&page=1&page_size=20`);
      setSkillResults(d.data || []);
    } catch {}
  };

  const toggleMem = (m: any) => {
    const next = new Map(stagedMem);
    if (next.has(m.id)) { next.delete(m.id); } else {
      next.set(m.id, { summary: m.summary_l0 || m.content?.slice(0, 80), content: m.content || '', context: m.context || '', resolution: m.resolution || '', type: m.memory_type, tier: m.tier, tags: m.tags || [] });
    }
    setStagedMem(next);
  };

  const toggleSkill = (s: any) => {
    const next = new Map(stagedSkill);
    if (next.has(s.id)) { next.delete(s.id); } else {
      next.set(s.id, {
        name: s.name,
        description: s.description || '',
        source: s.source,
        sourceType: s.source_type || '',
        fullName: s.id || '',
        categories: s.categories || [],
      });
    }
    setStagedSkill(next);
  };

  const toggleRole = (preset: RolePreset, categoryId: string) => {
    if (categoryId === 'mbti') {
      setSelectedMbti(prev => prev?.id === preset.id ? null : preset);
    } else if (categoryId === 'zodiac') {
      setSelectedZodiac(prev => prev?.id === preset.id ? null : preset);
    } else {
      if (selectedRole?.id === preset.id) {
        setSelectedRole(null);
        setSelectedRoleCat('');
      } else {
        setSelectedRole(preset);
        setSelectedRoleCat(categoryId);
      }
    }
  };

  const removeMem = (id: string) => { const n = new Map(stagedMem); n.delete(id); setStagedMem(n); };
  const removeSkill = (id: string) => { const n = new Map(stagedSkill); n.delete(id); setStagedSkill(n); };

  const selectedRoles = [selectedRole, selectedMbti, selectedZodiac].filter(Boolean) as RolePreset[];
  const roleCount = selectedRoles.length;

  const apply = async () => {
    if (!agentId) { alert(t('harness.compose.alertAgent')); return; }
    if (stagedMem.size === 0 && stagedSkill.size === 0 && roleCount === 0) { alert(t('harness.compose.alertPick')); return; }
    setBusy(true); setStatus(t('harness.compose.statusBuilding')); setStatusCls('');
    let resources: Record<string, string> = {};
    try {
      const d = await api(`/harness/profile?agent_id=${encodeURIComponent(agentId)}`);
      if (d.success && d.data) resources = d.data.resources || {};
    } catch {}

    if (stagedMem.size > 0) {
      let mc = resources['memory/MEMORY.md'] || '# Long-term Memory\n\n';
      mc += '\n## Imported from Collective Hub\n\n';
      for (const [id, m] of stagedMem) {
        mc += `### ${m.summary || id}\n\n`;
        if (m.content) mc += m.content + '\n\n';
        if (m.context) mc += `**Context:** ${m.context}\n\n`;
        if (m.resolution) mc += `**Resolution:** ${m.resolution}\n\n`;
        if (m.tags.length) mc += `*Tags: ${m.tags.join(', ')}*\n\n`;
        mc += '---\n\n';
      }
      resources['memory/MEMORY.md'] = mc;
    }

    if (stagedSkill.size > 0) {
      const modelscopeSkills: Array<{ full_name: string }> = [];
      for (const [id, s] of stagedSkill) {
        const isModelscope = s.sourceType === 'modelscope' || s.source === 'catalog';
        if (isModelscope && s.fullName) {
          modelscopeSkills.push({ full_name: s.fullName });
          continue;
        }
        const safeName = id.replace(/[^a-zA-Z0-9_-]/g, '_');
        const path = `skills/${safeName}/SKILL.md`;
        if (!resources[path]) {
          let sc = `# ${s.name}\n\n`;
          if (s.description) sc += `${s.description}\n\n`;
          if (s.categories.length) sc += `**Categories:** ${s.categories.join(', ')}\n\n`;
          sc += `**Source:** ${s.source}\n**ID:** ${id}\n`;
          resources[path] = sc;
        }
      }
      if (modelscopeSkills.length > 0) {
        resources['skills/.ultron_modelscope_imports.json'] = JSON.stringify(modelscopeSkills, null, 2);
      }
    }

    if (roleCount > 0) {
      try {
        const d = await apiPost('/harness/soul-presets/build', {
          preset_ids: selectedRoles.map(r => r.id),
        });
        if (d.success && d.data?.resources) {
          for (const [path, content] of Object.entries(d.data.resources)) {
            if (resources[path]) {
              resources[path] += '\n' + (content as string);
            } else {
              resources[path] = content as string;
            }
          }
        }
      } catch {}
    }

    setStatus(t('harness.compose.statusUploading'));
    const product = profiles.find(p => p.agent_id === agentId)?.product || 'nanobot';
    try {
      const d = await apiPost('/harness/sync/up', { agent_id: agentId, product, resources });
      if (d.success) {
        setStatus(formatTemplate(t('harness.compose.statusDone'), {
          mem: stagedMem.size,
          skill: stagedSkill.size,
          role: roleCount,
          rev: d.data?.revision ?? '?',
        }));
        setStatusCls('text-accent');
        setStagedMem(new Map()); setStagedSkill(new Map());
        setSelectedRole(null); setSelectedRoleCat(''); setSelectedMbti(null); setSelectedZodiac(null);
      } else { setStatus(d.detail || t('harness.compose.statusFailed')); setStatusCls('text-danger'); }
    } catch { setStatus(t('harness.compose.uploadFailed')); setStatusCls('text-danger'); }
    setBusy(false);
  };

  const total = stagedMem.size + stagedSkill.size + roleCount;

  // Filter roles by category and text
  const filteredCategories = roleCategories
    .filter(c => !roleCatFilter || c.id === roleCatFilter);

  return (
    <div className="card-panel p-5 space-y-4">
      <div>
        <span className="kicker">{t('harness.compose.kicker')}</span>
        <HarnessIoBlurb inputKey="harness.compose.input" outputKey="harness.compose.output" />
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <AgentIdCombo value={agentId} onChange={setAgentId} profiles={profiles} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Memories panel */}
        <div className="bg-paper rounded-card-sm p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold">{t('harness.compose.memories')}</h4>
            <span className="chip">{stagedMem.size} {t('harness.compose.selected')}</span>
          </div>
          <div className="flex gap-2">
            <input placeholder={t('harness.compose.searchMemories')} value={memQuery} onChange={e => setMemQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && searchMem()} className="flex-1 text-xs" />
            <button type="button" className="btn-primary text-xs px-2 py-1" onClick={searchMem}>{t('harness.compose.search')}</button>
          </div>
          <div className="max-h-[280px] overflow-y-auto space-y-1">
            {memResults.length === 0 ? (
              <p className="text-xs text-mid-gray text-center py-4">{t('harness.compose.hintMemories')}</p>
            ) : memResults.map(m => (
              <label key={m.id} className="flex items-start gap-2 p-2 rounded hover:bg-warm-gray cursor-pointer transition-colors">
                <input type="checkbox" checked={stagedMem.has(m.id)} onChange={() => toggleMem(m)} className="mt-0.5 accent-primary" />
                <div className="min-w-0">
                  <div className="text-xs font-medium truncate">{m.summary_l0 || m.content?.slice(0, 80)}</div>
                  <div className="text-xs text-muted">{m.memory_type} · {m.tier} · {formatTemplate(t('harness.compose.hits'), { n: m.hit_count })}</div>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Skills panel */}
        <div className="bg-paper rounded-card-sm p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold">{t('harness.compose.skills')}</h4>
            <span className="chip">{stagedSkill.size} {t('harness.compose.selected')}</span>
          </div>
          <div className="flex gap-2">
            <input placeholder={t('harness.compose.searchSkills')} value={skillQuery} onChange={e => setSkillQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && searchSkill()} className="flex-1 text-xs" />
            <button type="button" className="btn-primary text-xs px-2 py-1" onClick={searchSkill}>{t('harness.compose.search')}</button>
          </div>
          <div className="max-h-[280px] overflow-y-auto space-y-1">
            {skillResults.length === 0 ? (
              <p className="text-xs text-mid-gray text-center py-4">{t('harness.compose.hintSkills')}</p>
            ) : skillResults.map(s => (
              <label key={s.id} className="flex items-start gap-2 p-2 rounded hover:bg-warm-gray cursor-pointer transition-colors">
                <input type="checkbox" checked={stagedSkill.has(s.id)} onChange={() => toggleSkill(s)} className="mt-0.5 accent-primary" />
                <div className="min-w-0">
                  <div className="text-xs font-medium truncate">{s.name}</div>
                  <div className="text-xs text-muted">{s.source}{s.categories?.length ? ' · ' + s.categories.join(', ') : ''}</div>
                </div>
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* Roles — three independent pick-one sections */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Role (professional / divination) */}
        <div className="bg-paper rounded-card-sm p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold">{t('harness.compose.role')}</h4>
            {selectedRole && <span className="chip">{selectedRole.emoji} {selectedRole.name.slice(0, 20)}</span>}
          </div>
          <div className="flex gap-2">
            <select
              value={roleCatFilter}
              onChange={e => setRoleCatFilter(e.target.value)}
              className="text-xs bg-surface border border-border rounded px-2 py-1 flex-1"
            >
              <option value="">{t('harness.compose.allCategories')}</option>
              {roleCategories.filter(c => !PERSONALITY_CATEGORIES.has(c.id)).map(c => (
                <option key={c.id} value={c.id}>{c.label} ({c.presets.length})</option>
              ))}
            </select>
          </div>
          <div className="max-h-[280px] overflow-y-auto px-1 space-y-1">
            {filteredCategories.filter(c => !PERSONALITY_CATEGORIES.has(c.id)).length === 0 ? (
              <p className="text-xs text-mid-gray text-center py-4">{t('harness.compose.hintRoles')}</p>
            ) : filteredCategories.filter(c => !PERSONALITY_CATEGORIES.has(c.id)).map(cat => (
              <div key={cat.id}>
                <div className="text-xs text-muted font-semibold px-2 py-1 bg-paper">{cat.label}</div>
                {cat.presets.map(p => (
                  <button key={p.id} type="button"
                    title={`${p.name}\n${p.description}`}
                    className={`w-full text-left flex items-center gap-2 p-2 rounded cursor-pointer transition-colors bg-transparent border-none ${selectedRole?.id === p.id ? 'bg-[rgba(13,148,136,0.1)] ring-1 ring-accent' : 'hover:bg-warm-gray'}`}
                    onClick={() => toggleRole(p, cat.id)}
                  >
                    <span className="text-base flex-shrink-0">{p.emoji || '🎭'}</span>
                    <div className="min-w-0">
                      <div className="text-xs font-medium truncate">{p.name}</div>
                    </div>
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>

        {/* MBTI */}
        <div className="bg-paper rounded-card-sm p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold">MBTI</h4>
            {selectedMbti && <span className="chip">🧠 {selectedMbti.name.slice(0, 20)}</span>}
          </div>
          <div className="max-h-[320px] overflow-y-auto px-1 space-y-1">
            {(roleCategories.find(c => c.id === 'mbti')?.presets || []).map(p => (
              <button key={p.id} type="button"
                title={`${p.name}\n${p.description}`}
                className={`w-full text-left flex items-center gap-2 p-2 rounded cursor-pointer transition-colors bg-transparent border-none ${selectedMbti?.id === p.id ? 'bg-[rgba(13,148,136,0.1)] ring-1 ring-accent' : 'hover:bg-warm-gray'}`}
                onClick={() => toggleRole(p, 'mbti')}
              >
                <span className="text-base flex-shrink-0">{p.emoji || '🧠'}</span>
                <div className="min-w-0">
                  <div className="text-xs font-medium truncate">{p.name}</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Zodiac */}
        <div className="bg-paper rounded-card-sm p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold">{t('harness.compose.zodiac')}</h4>
            {selectedZodiac && <span className="chip">{selectedZodiac.emoji} {selectedZodiac.name.slice(0, 20)}</span>}
          </div>
          <div className="max-h-[320px] overflow-y-auto px-1 space-y-1">
            {(roleCategories.find(c => c.id === 'zodiac')?.presets || []).map(p => (
              <button key={p.id} type="button"
                title={`${p.name}\n${p.description}`}
                className={`w-full text-left flex items-center gap-2 p-2 rounded cursor-pointer transition-colors bg-transparent border-none ${selectedZodiac?.id === p.id ? 'bg-[rgba(13,148,136,0.1)] ring-1 ring-accent' : 'hover:bg-warm-gray'}`}
                onClick={() => toggleRole(p, 'zodiac')}
              >
                <span className="text-base flex-shrink-0">{p.emoji}</span>
                <div className="min-w-0">
                  <div className="text-xs font-medium truncate">{p.name}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {total > 0 && (
      <div className="bg-surface border border-border rounded-card-sm p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold">{t('harness.compose.staging')}</h4>
          <span className="text-xs text-muted">{total} {t('harness.compose.items')}</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {Array.from(stagedMem.entries()).map(([id, m]) => (
            <span key={id} className="chip border-accent bg-[rgba(13,148,136,0.06)]">
              &#x1F4DD; {(m.summary || id).slice(0, 40)}
              <button className="text-danger bg-transparent border-none text-xs ml-1" onClick={() => removeMem(id)}>×</button>
            </span>
          ))}
          {Array.from(stagedSkill.entries()).map(([id, s]) => (
            <span key={id} className="chip border-sage bg-[rgba(188,210,203,0.1)]">
              &#x2699; {(s.name || id).slice(0, 40)}
              <button className="text-danger bg-transparent border-none text-xs ml-1" onClick={() => removeSkill(id)}>×</button>
            </span>
          ))}
          {selectedRole && (
            <span className="chip border-primary bg-[rgba(99,102,241,0.06)]">
              &#x1F3AD; {selectedRole.emoji} {selectedRole.name.slice(0, 30)}
              <button className="text-danger bg-transparent border-none text-xs ml-1" onClick={() => { setSelectedRole(null); setSelectedRoleCat(''); }}>×</button>
            </span>
          )}
          {selectedMbti && (
            <span className="chip border-primary bg-[rgba(99,102,241,0.06)]">
              &#x1F9E0; {selectedMbti.name.slice(0, 30)}
              <button className="text-danger bg-transparent border-none text-xs ml-1" onClick={() => setSelectedMbti(null)}>×</button>
            </span>
          )}
          {selectedZodiac && (
            <span className="chip border-primary bg-[rgba(99,102,241,0.06)]">
              {selectedZodiac.emoji} {selectedZodiac.name.slice(0, 30)}
              <button className="text-danger bg-transparent border-none text-xs ml-1" onClick={() => setSelectedZodiac(null)}>×</button>
            </span>
          )}
        </div>
      </div>
      )}

      <div className="flex items-center gap-3">
        <button type="button" className="btn-primary text-sm" onClick={apply} disabled={busy}>{t('harness.compose.apply')}</button>
        {status && <span className={`text-sm ${statusCls || 'text-muted'}`}>{status}</span>}
      </div>
    </div>
  );
}
