import { useLocale } from '../contexts/LocaleContext';
import { formatTemplate } from '../i18n/translations';

interface PaginationProps {
  page: number;
  total: number;
  pageSize: number;
  onChange: (page: number) => void;
}

export default function Pagination({ page, total, pageSize, onChange }: PaginationProps) {
  const { t } = useLocale();
  const pages = Math.ceil(total / pageSize);
  if (pages <= 1) return null;

  return (
    <div className="flex items-center justify-center gap-3 mt-6 text-sm">
      <button
        className="btn-outline px-3 py-1 text-xs"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        {t('pagination.prev')}
      </button>
      <span className="text-muted">
        {formatTemplate(t('pagination.pageOf'), { page, pages, total })}
      </span>
      <button
        className="btn-outline px-3 py-1 text-xs"
        disabled={page >= pages}
        onClick={() => onChange(page + 1)}
      >
        {t('pagination.next')}
      </button>
    </div>
  );
}
