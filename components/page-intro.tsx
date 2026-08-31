import type { ReactNode } from 'react';

export function PageIntro({
  kicker,
  title,
  children,
  actions,
}: {
  kicker: string;
  title: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="page-intro">
      <div>
        <p className="kicker">{kicker}</p>
        <h1>{title}</h1>
        <div className="lede">{children}</div>
      </div>
      {actions && <div className="intro-actions">{actions}</div>}
    </section>
  );
}
