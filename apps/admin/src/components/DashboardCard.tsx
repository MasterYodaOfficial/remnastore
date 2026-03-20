type DashboardCardProps = {
  label: string;
  value: string | number;
  hint: string;
};

export function DashboardCard({ label, value, hint }: DashboardCardProps) {
  return (
    <article className="metric-card">
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      <span className="metric-hint">{hint}</span>
    </article>
  );
}
