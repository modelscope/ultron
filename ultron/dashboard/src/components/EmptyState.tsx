interface EmptyStateProps {
  title: string;
  description?: string;
}

export default function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="text-center py-10">
      <div className="text-muted font-serif text-lg">{title}</div>
      {description && <div className="text-sm text-mid-gray mt-2">{description}</div>}
    </div>
  );
}
