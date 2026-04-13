import { useMemo, useState } from 'react';
import { useLocale } from '../contexts/LocaleContext';

const SKILL_DOWNLOAD_PATH = '/dashboard/agent-skill-package';

const EXPORT_ULTRON_URL = 'export ULTRON_API_URL=https://writtingforfun-ultron.ms.show';

/** Keep in sync with skills/ultron-1.0.0 in the repo (also packaged by /dashboard/agent-skill-package). */
const ULTRON_SKILL_PACKAGE_TREE = `ultron-1.0.0/
├── SKILL.md
├── setup.md
├── boundaries.md
├── operations.md
└── scripts/
    ├── ultron_client.py
    └── memory_sync.py`;

type AgentChoice = 'openclaw' | 'nanobot' | 'hermes';

const AGENT_ORDER: AgentChoice[] = ['openclaw', 'nanobot', 'hermes'];

const AGENT_LABEL: Record<AgentChoice, string> = {
  openclaw: 'OpenClaw',
  nanobot: 'Nanobot',
  hermes: 'Hermes',
};

function copyCommandForAgent(agent: AgentChoice): string {
  switch (agent) {
    case 'openclaw':
      return 'cp -r ./ultron-1.0.0 ~/.openclaw/workspace/skills/';
    case 'nanobot':
      return 'cp -r ./ultron-1.0.0 ~/.nanobot/workspace/skills/';
    case 'hermes':
      return 'mkdir -p ~/.hermes/skills && cp -r ./ultron-1.0.0 ~/.hermes/skills/';
    default:
      return 'cp -r ./ultron-1.0.0 ~/.nanobot/workspace/skills/';
  }
}

function CopyButton({ target }: { target: string }) {
  const { t } = useLocale();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(target);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {}
  };
  return (
    <button type="button" className="btn-outline text-xs shrink-0" onClick={copy}>
      {copied ? t('quickstart.copied') : t('quickstart.copy')}
    </button>
  );
}

const numColors = [
  'bg-primary text-bg-page',
  'bg-accent text-bg-page',
  'bg-teal text-ink',
  'bg-oxide text-bg-page',
];

export default function QuickstartPage() {
  const { t } = useLocale();
  const [agent, setAgent] = useState<AgentChoice>('nanobot');
  const copyCmd = useMemo(() => copyCommandForAgent(agent), [agent]);

  const stepsTail = useMemo(
    () => [
      {
        num: '3',
        title: t('quickstart.step3Title'),
        desc: t('quickstart.step3Desc'),
        code: t('quickstart.step3Code'),
        isMsg: true,
        bullets: [t('quickstart.bullet1'), t('quickstart.bullet2'), t('quickstart.bullet3')],
      },
      {
        num: '4',
        title: t('quickstart.step4Title'),
        desc: t('quickstart.step4Desc'),
        code: t('quickstart.step4Prompt'),
        exampleOutput: t('quickstart.step4Example'),
      },
    ],
    [t],
  );

  return (
    <div className="p-6 space-y-6 max-w-[1200px] mx-auto">
      <div>
        <h1 className="text-3xl font-bold font-serif">{t('quickstart.title')}</h1>
        <p className="text-sm text-muted mt-2 max-w-[min(100%,52rem)]">
          {t('quickstart.introPart1')}
          <code className="text-primary text-xs">ULTRON_API_URL</code>
          {t('quickstart.introPart2')}
          <code className="text-primary text-xs">setup.md</code>
          {t('quickstart.introPart3')}
        </p>
      </div>

      <ol className="grid grid-cols-1 md:grid-cols-2 gap-5 lg:gap-6 list-none p-0 m-0 max-w-6xl mx-auto">
        <li className="flex min-h-0">
          <div className="card-panel p-5 space-y-3 hover:shadow-soft transition-shadow flex flex-col h-full w-full">
            <div className="flex items-start gap-3">
              <span
                className={`w-9 h-9 rounded-xl flex items-center justify-center text-sm font-bold flex-shrink-0 shadow-sm ${numColors[0]}`}
                aria-hidden
              >
                1
              </span>
              <div className="min-w-0 pt-0.5">
                <h3 className="font-semibold text-sm leading-snug">{t('quickstart.step1Title')}</h3>
                <p className="text-xs text-muted mt-1.5 leading-relaxed">{t('quickstart.step1Desc')}</p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <a
                href={SKILL_DOWNLOAD_PATH}
                download="ultron-1.0.0.zip"
                className="btn-primary text-sm no-underline inline-flex items-center"
              >
                {t('quickstart.downloadZip')}
              </a>
              <span className="text-xs text-muted">{t('quickstart.zipHint')}</span>
            </div>

            <div className="pt-3 border-t border-border/60 flex-1 flex flex-col min-h-0 mt-1">
              <p className="text-[11px] font-semibold text-ink mb-2">{t('quickstart.packageContents')}</p>
              <pre
                className="text-[11px] m-0 p-3 rounded-card-sm bg-paper font-mono text-accent leading-relaxed whitespace-pre border border-border/40 overflow-x-auto flex-1"
                aria-label="ultron-1.0.0 file tree"
              >
                {ULTRON_SKILL_PACKAGE_TREE}
              </pre>
            </div>
          </div>
        </li>

        <li className="flex min-h-0">
          <div className="card-panel p-5 space-y-3 hover:shadow-soft transition-shadow flex flex-col h-full w-full">
            <div className="flex items-start gap-3">
              <span
                className={`w-9 h-9 rounded-xl flex items-center justify-center text-sm font-bold flex-shrink-0 shadow-sm ${numColors[1]}`}
                aria-hidden
              >
                2
              </span>
              <div className="min-w-0 pt-0.5">
                <h3 className="font-semibold text-sm leading-snug">{t('quickstart.step2Title')}</h3>
                <p className="text-xs text-muted mt-1.5 leading-relaxed">{t('quickstart.step2Desc')}</p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor="agent-workspace" className="text-xs font-medium text-ink">
                {t('quickstart.agentWorkspace')}
              </label>
              <select
                id="agent-workspace"
                value={agent}
                onChange={e => setAgent(e.target.value as AgentChoice)}
                className="text-xs min-w-[140px] py-1.5 px-2 rounded-card-sm border border-border bg-surface"
              >
                {AGENT_ORDER.map(key => (
                  <option key={key} value={key}>
                    {AGENT_LABEL[key]}
                  </option>
                ))}
              </select>
            </div>

            <p className="text-xs text-muted leading-relaxed">
              {t('quickstart.parentDirHint')}
            </p>

            <div className="flex items-center gap-3 p-3 rounded-card-sm bg-paper">
              <pre className="flex-1 min-w-0 text-xs m-0 whitespace-pre-wrap break-all bg-transparent text-accent">{copyCmd}</pre>
              <CopyButton target={copyCmd} />
            </div>

            <p className="text-xs font-medium text-ink pt-1">{t('quickstart.apiEndpoint')}</p>

            <div className="flex items-center gap-3 p-3 rounded-card-sm bg-paper">
              <pre className="flex-1 min-w-0 text-xs m-0 whitespace-pre-wrap break-all bg-transparent text-accent">
                {EXPORT_ULTRON_URL}
              </pre>
              <CopyButton target={EXPORT_ULTRON_URL} />
            </div>
          </div>
        </li>

        {stepsTail.map((step, i) => (
          <li key={step.num} className="flex min-h-0">
            <div className="card-panel p-5 space-y-3 hover:shadow-soft transition-shadow flex flex-col h-full w-full">
              <div className="flex items-start gap-3">
                <span
                  className={`w-9 h-9 rounded-xl flex items-center justify-center text-sm font-bold flex-shrink-0 shadow-sm ${numColors[i + 2]}`}
                  aria-hidden
                >
                  {step.num}
                </span>
                <div className="min-w-0 pt-0.5">
                  <h3 className="font-semibold text-sm leading-snug">{step.title}</h3>
                  <p className="text-xs text-muted mt-1.5 leading-relaxed">{step.desc}</p>
                </div>
              </div>
              <div
                className={`flex items-center gap-3 p-3 rounded-card-sm ${
                  'isMsg' in step && step.isMsg
                    ? 'bg-warm-gray border-l-[3px] border-gold'
                    : 'bg-paper'
                }`}
              >
                <pre
                  className={`flex-1 min-w-0 text-xs m-0 whitespace-pre-wrap break-all bg-transparent ${
                    'isMsg' in step && step.isMsg ? 'text-oxide' : 'text-accent'
                  }`}
                >
                  {step.code}
                </pre>
                <CopyButton target={step.code} />
              </div>
              {'exampleOutput' in step && step.exampleOutput && (
                <pre className="text-xs m-0 p-3 rounded-card-sm bg-paper/80 text-muted whitespace-pre-wrap break-words border border-border/50 leading-relaxed">
                  {step.exampleOutput}
                </pre>
              )}
              {'bullets' in step && step.bullets && (
                <ul className="text-xs text-muted space-y-1.5 pl-4 list-disc mt-auto pt-2 border-t border-border/60">
                  {step.bullets.map((b, j) => (
                    <li key={j} className="leading-relaxed">
                      {b}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        ))}
      </ol>

      <div className="flex flex-wrap items-center justify-between gap-4 pt-4 border-t border-border">
        <p className="text-sm text-muted max-w-[min(100%,52rem)] min-w-0 flex-1">
          {t('quickstart.footer')}
        </p>
        <a
          href="https://github.com/vinci-grape/ultron/blob/main/docs/zh/GetStarted/AgentSetup.md"
          target="_blank"
          rel="noopener noreferrer"
          className="btn-primary text-sm no-underline"
        >
          {t('quickstart.docsLink')}
        </a>
      </div>
    </div>
  );
}
