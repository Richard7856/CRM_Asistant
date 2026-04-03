interface EmptyStateProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export default function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="neu-pressed w-16 h-16 rounded-full flex items-center justify-center mb-4">
        <span className="text-2xl text-[var(--text-muted)]">0</span>
      </div>
      <h3 className="text-base font-semibold text-[var(--text-primary)]">{title}</h3>
      {description && <p className="mt-1 text-sm text-[var(--text-secondary)]">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
