import { useState, type FormEvent, type ChangeEvent } from "react";
import { Button } from "../components/Button";

interface Props {
  onLogin: (email: string, password: string) => Promise<void>;
  onCreateAccount: () => void;
}

export function LoginPage({ onLogin, onCreateAccount }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setLoading(true);
    try { await onLogin(email, password); } catch (err) { setError(err instanceof Error ? err.message : "Erro ao entrar"); } finally { setLoading(false); }
  }

  return <section className="auth-shell">
    <div className="auth-art hidden md:flex">
      <div className="relative z-10 max-w-sm">
        <span className="eyebrow">REaleza · BARBERS</span>
        <h1 className="mt-5 text-5xl font-black leading-[1.05]">Seu estilo.<br /><span className="text-violet-300">Sua realeza.</span></h1>
        <p className="mt-5 leading-7 text-zinc-300">Um atendimento de respeito, um corte à altura. Entre para gerenciar seus horários e viver a experiência Realeza.</p>
        <div className="mt-10 flex items-center gap-3 text-sm text-zinc-300"><span className="h-px w-10 bg-violet-400" /> Cuidado nos detalhes, sempre.</div>
      </div>
      <div className="auth-art-ring" aria-hidden="true" />
    </div>
    <div className="auth-form-panel">
      <div className="mb-8 md:hidden"><span className="eyebrow text-violet-700">REaleza · BARBERS</span></div>
      <span className="text-sm font-bold uppercase tracking-[0.2em] text-violet-700">Bem-vindo de volta</span>
      <h2 className="mt-3 text-3xl font-black tracking-tight text-zinc-950">Entrar na sua conta</h2>
      <p className="mt-2 text-sm leading-6 text-zinc-500">Acesse sua conta para agendar e acompanhar seus horários.</p>
      <form onSubmit={submit} className="mt-8 space-y-5">
        <label className="field-label">E-mail
          <input autoComplete="email" value={email} onChange={(e: ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)} className="field-input" type="email" placeholder="voce@exemplo.com" required />
        </label>
        <label className="field-label">Senha
          <input autoComplete="current-password" value={password} onChange={(e: ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)} className="field-input" type="password" placeholder="Sua senha" required />
        </label>
        {error && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        <Button disabled={loading} className="w-full !rounded-xl !py-3.5">{loading ? "Entrando..." : "Entrar"}</Button>
      </form>
      <p className="mt-7 text-center text-sm text-zinc-500">Ainda não tem conta? <button onClick={onCreateAccount} className="font-bold text-violet-700 hover:text-violet-800">Criar conta</button></p>
    </div>
  </section>;
}
