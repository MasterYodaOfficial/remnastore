type DetailFactProps = {
  label: string;
  value: string;
};

export function DetailFact({ label, value }: DetailFactProps) {
  return (
    <div className="detail-fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
