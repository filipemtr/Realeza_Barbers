import { useState, type ChangeEvent, type FormEvent } from "react";
import { Button } from "../components/Button";

interface Props {
  onRegister: (email: string, password: string) => Promise<void>;
  onBackToLogin: () => void;
}

export function RegisterPage({ onRegister, onBackToLogin }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (password !== confirmPassword) { setError("As senhas não coincidem."); return; }
    if (new TextEncoder().encode(password).length > 72) { setError("A senha deve ter no máximo 72 bytes."); return; }
    setLoading(true);
    try { await onRegister(email, password); } catch (err) { setError(err instanceof Error ? err.message : "Não foi possível criar a conta."); } finally { setLoading(false); }
  }

  return <section className="auth-shell">
    <div className="auth-art register-art hidden md:flex">
      <div className="relative z-10 max-w-sm">
        <span className="eyebrow">FAÇA PARTE</span>
        <h1 className="mt-5 text-5xl font-black leading-[1.05]">O próximo nível do <span className="text-violet-300">seu estilo.</span></h1>
        <p className="mt-5 leading-7 text-zinc-300">Crie sua conta gratuitamente e deixe seus próximos horários organizados em poucos cliques.</p>
        <ul className="mt-8 space-y-3 text-sm text-zinc-200"><li>✦ Agende quando quiser</li><li>✦ Consulte seus horários</li><li>✦ Mais praticidade, menos espera</li></ul>
      </div>
      <div className="auth-art-ring" aria-hidden="true" />
    </div>
    <div className="auth-form-panel">
      <div className="mb-8 md:hidden"><span className="eyebrow text-violet-700">REaleza · BARBERS</span></div>
      <span className="text-sm font-bold uppercase tracking-[0.2em] text-violet-700">Cadastro de cliente</span>
      <h2 className="mt-3 text-3xl font-black tracking-tight text-zinc-950">Crie sua conta</h2>
      <p className="mt-2 text-sm leading-6 text-zinc-500">Preencha os dados abaixo para começar a agendar.</p>
      <form onSubmit={submit} className="mt-8 space-y-5">
        <label className="field-label">E-mail
          <input autoComplete="email" value={email} onChange={(e: ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)} className="field-input" type="email" placeholder="voce@exemplo.com" required />
        </label>
        <label className="field-label">Senha <span className="font-normal text-zinc-400">(mínimo de 8 caracteres)</span>
          <input autoComplete="new-password" value={password} onChange={(e: ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)} className="field-input" type="password" minLength={8} required />
        </label>
        <label className="field-label">Confirmar senha
          <input autoComplete="new-password" value={confirmPassword} onChange={(e: ChangeEvent<HTMLInputElement>) => setConfirmPassword(e.target.value)} className="field-input" type="password" minLength={8} required />
        </label>
        {error && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        <Button disabled={loading} className="w-full !rounded-xl !py-3.5">{loading ? "Criando conta..." : "Criar conta grátis"}</Button>
      </form>
      <p className="mt-7 text-center text-sm text-zinc-500">Já tem uma conta? <button onClick={onBackToLogin} className="font-bold text-violet-700 hover:text-violet-800">Entrar</button></p>
      <p className="mt-4 text-center text-xs leading-5 text-zinc-400">O cadastro público cria uma conta de cliente. Perfis de barbeiro e administrador são gerenciados separadamente.</p>
    </div>
  </section>;
}
