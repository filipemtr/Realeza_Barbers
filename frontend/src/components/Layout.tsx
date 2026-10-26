import type { ReactNode } from "react";
import type { User } from "../types/api";
import { BrandMark } from "./BrandMark";

interface Props { user: User | null; onLogout: () => void; children: ReactNode; onHome: () => void; }

export function Layout({ user, onLogout, children, onHome }: Props) {
  return <div className="app-shell">
    <header className="site-header">
      <div className="header-inner">
        <button onClick={onHome} className="brand-lockup" aria-label="Ir para a página inicial"><span className="brand-symbol"><BrandMark /></span><span className="brand-type"><strong>REALEZA</strong><small>BARBERS</small></span></button>
        <nav className="header-nav" aria-label="Navegação principal"><button onClick={onHome}>Início</button><button onClick={() => document.getElementById("servicos")?.scrollIntoView({ behavior: "smooth" })}>Serviços</button></nav>
        <div className="header-account">{user ? <><span className="header-user-email">{user.email}</span><span className="role-chip">{user.role === "user" ? "Cliente" : user.role === "barber" ? "Barbeiro" : "Admin"}</span><button onClick={onLogout} className="header-login-button">Sair <span aria-hidden="true">↗</span></button></> : <span className="header-tagline">SEU ESTILO. SUA ASSINATURA.</span>}</div>
      </div>
    </header>
    <main className="site-main">{children}</main>
    <footer className="site-footer"><div className="footer-brand"><span className="brand-symbol"><BrandMark /></span><div><strong>REALEZA BARBERS</strong><small>Estilo em cada detalhe.</small></div></div><p>© {new Date().getFullYear()} Realeza Barbers. Feito para quem sabe o seu valor.</p><button onClick={onHome}>Voltar ao topo ↑</button></footer>
  </div>;
}
