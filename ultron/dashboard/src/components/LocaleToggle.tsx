import { useLocale } from '../contexts/LocaleContext';
import type { Locale } from '../i18n/translations';

export default function LocaleToggle() {
  const { locale, setLocale } = useLocale();

  const btn = (l: Locale, label: string) => (
    <button
      type="button"
      key={l}
      className={`px-2.5 py-1 text-xs font-medium transition-colors ${
        locale === l
          ? 'bg-primary text-bg-page'
          : 'text-muted hover:text-ink hover:bg-paper'
      }`}
      onClick={() => setLocale(l)}
      aria-pressed={locale === l}
    >
      {label}
    </button>
  );

  return (
    <div
      className="inline-flex items-center overflow-hidden rounded-card-sm border border-border bg-surface p-0.5 gap-0.5"
      role="group"
      aria-label="Language"
    >
      {btn('en', 'EN')}
      {btn('zh', '中文')}
    </div>
  );
}
