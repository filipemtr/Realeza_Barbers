/** Marca vetorial leve: tesoura com coroa, sem dependência de biblioteca de ícones. */
export function BrandMark({ className = "", title = "Realeza Barbers" }: { className?: string; title?: string }) {
  return (
    <svg className={className} viewBox="0 0 48 48" role="img" aria-label={title} fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M10 9.5 15.5 15 21 9.5 26.5 15 32 9.5 34 19H8L10 9.5Z" fill="currentColor" opacity=".95" />
      <path d="M10.5 24.5 30.5 43M37.5 24.5 17.5 43" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" />
      <circle cx="8.5" cy="22.5" r="4.3" stroke="currentColor" strokeWidth="2.8" />
      <circle cx="39.5" cy="22.5" r="4.3" stroke="currentColor" strokeWidth="2.8" />
      <circle cx="24" cy="31" r="2.2" fill="currentColor" />
    </svg>
  );
}
