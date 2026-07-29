export function LoadingDots({ label = "处理中" }: { label?: string }) {
  return (
    <span className="loading-dots" role="status" aria-label={label}>
      <i />
      <i />
      <i />
    </span>
  );
}
