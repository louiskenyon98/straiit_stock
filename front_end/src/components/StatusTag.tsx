export function StatusTag({ status, label }: { status: string | null; label: string | null }) {
  if (!label) return null
  const tone = status === 'AVAILABLE'
    ? 'tag-accent'
    : status === 'NOT_AVAILABLE'
      ? 'tag-neutral'
      : status === 'LAST_PIECES'
        ? 'tag-outline'
        : 'tag-accent-soft'
  return <span className={`tag ${tone}`}>{label}</span>
}
