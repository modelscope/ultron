import { useState } from 'react';
import { useLocale } from '../../contexts/LocaleContext';

export default function HarnessIoBlurb({ inputKey, outputKey }: { inputKey: string; outputKey: string }) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);

  return (
    <button
      type="button"
      className="inline-flex items-center gap-1 ml-2 align-middle text-muted hover:text-ink transition-colors cursor-pointer bg-transparent border-none p-0"
      onClick={() => setOpen(o => !o)}
      aria-expanded={open}
    >
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 opacity-50" aria-hidden>
        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.25a.25.25 0 01.25.25v1.5a.25.25 0 01-.25.25H9a.75.75 0 000 1.5h2a.75.75 0 000-1.5h-.25a.25.25 0 01-.25-.25v-2.5A.75.75 0 009.75 9H9z" clipRule="evenodd" />
      </svg>
      {open && (
        <span className="text-xs text-muted font-normal">
          {t('harness.ioLabelInput')}: {t(inputKey)} → {t('harness.ioLabelOutput')}: {t(outputKey)}
        </span>
      )}
    </button>
  );
}
