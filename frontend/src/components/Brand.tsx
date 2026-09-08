type BrandProps = { compact?: boolean };

export function Brand({ compact = false }: BrandProps) {
  return (
    <a
      className={compact ? "brand brand-compact" : "brand"}
      href="http://czon.cn"
      target="_blank"
      rel="noreferrer noopener"
      title="访问 czon.cn"
    >
      czon<span>.cn</span>
    </a>
  );
}
