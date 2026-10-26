import { useEffect, useState, type ChangeEvent } from "react";
import type { Role, Service, User } from "../types/api";
import { api } from "../services/api";
import { Button } from "../components/Button";

const emptyService = { name: "", description: "", price_cents: 0, duration_minutes: 30 };

export function AdminPage({ onBack }: { onBack: () => void }) {
  const [users, setUsers] = useState<User[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("user");
  const [service, setService] = useState(emptyService);
  const [message, setMessage] = useState("");

  async function load() {
    const [loadedUsers, loadedServices] = await Promise.all([api.adminUsers(), api.services()]);
    setUsers(loadedUsers);
    setServices(loadedServices);
  }

  useEffect(() => { load().catch(e => setMessage(e.message)); }, []);

  async function createUser() {
    try {
      const created = await api.createUser({ email, password, role, is_active: true });
      setUsers(items => [...items, created]);
      setEmail(""); setPassword(""); setMessage("Usuário criado.");
    } catch (e) { setMessage(e instanceof Error ? e.message : "Erro ao criar usuário"); }
  }

  async function toggleUser(item: User) {
    try {
      const updated = await api.updateUser(item.id, { is_active: !item.is_active });
      setUsers(items => items.map(current => current.id === item.id ? updated : current));
    } catch (e) { setMessage(e instanceof Error ? e.message : "Erro ao atualizar usuário"); }
  }

  async function removeUser(item: User) {
    if (!confirm(`Excluir ${item.email}?`)) return;
    try {
      await api.deleteUser(item.id);
      setUsers(items => items.filter(current => current.id !== item.id));
    } catch (e) { setMessage(e instanceof Error ? e.message : "Erro ao excluir usuário"); }
  }

  async function createService() {
    try {
      const created = await api.createService(service);
      setServices(items => [...items, created].sort((a, b) => a.name.localeCompare(b.name)));
      setService(emptyService);
      setMessage("Serviço criado.");
    } catch (e) { setMessage(e instanceof Error ? e.message : "Erro ao criar serviço"); }
  }

  async function toggleService(item: Service) {
    try {
      const updated = await api.updateService(item.id, { ...item, is_active: !item.is_active });
      setServices(items => items.map(current => current.id === item.id ? updated : current));
    } catch (e) { setMessage(e instanceof Error ? e.message : "Erro ao atualizar serviço"); }
  }

  return <div className="mx-auto max-w-6xl">
    <button onClick={onBack} className="text-sm font-semibold text-zinc-500">← Voltar</button>
    <h1 className="mt-3 text-4xl font-black">Administração</h1>
    {message && <p className="mt-4 rounded-xl bg-zinc-200 p-3 text-sm">{message}</p>}

    <div className="mt-7 grid gap-5 lg:grid-cols-2">
      <section className="rounded-2xl bg-white p-5 shadow-sm">
        <h2 className="font-bold">Usuários</h2>
        <div className="mt-4 space-y-3">
          <input placeholder="E-mail" value={email} onChange={(e: ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)} className="w-full rounded-xl border p-3" />
          <input placeholder="Senha" type="password" value={password} onChange={(e: ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)} className="w-full rounded-xl border p-3" />
          <select value={role} onChange={(e: ChangeEvent<HTMLSelectElement>) => setRole(e.target.value as Role)} className="w-full rounded-xl border p-3"><option value="user">Cliente</option><option value="barber">Barbeiro</option><option value="admin">Admin</option></select>
          <Button onClick={createUser} className="w-full">Cadastrar usuário</Button>
        </div>
        <div className="mt-6 divide-y">
          {users.map(item => <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
            <div><p className="font-semibold">{item.email}</p><p className="text-zinc-500">{item.role} · {item.is_active ? "ativo" : "inativo"}</p></div>
            <div className="flex gap-2"><Button variant="secondary" onClick={() => toggleUser(item)}>{item.is_active ? "Desativar" : "Ativar"}</Button><Button variant="danger" onClick={() => removeUser(item)}>Excluir</Button></div>
          </div>)}
        </div>
      </section>

      <section className="rounded-2xl bg-white p-5 shadow-sm">
        <h2 className="font-bold">Serviços</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <input placeholder="Nome" value={service.name} onChange={(e: ChangeEvent<HTMLInputElement>) => setService({ ...service, name: e.target.value })} className="rounded-xl border p-3" />
          <input placeholder="Preço em centavos" type="number" min="0" value={service.price_cents} onChange={(e: ChangeEvent<HTMLInputElement>) => setService({ ...service, price_cents: Number(e.target.value) })} className="rounded-xl border p-3" />
          <input placeholder="Duração em minutos" type="number" min="1" value={service.duration_minutes} onChange={(e: ChangeEvent<HTMLInputElement>) => setService({ ...service, duration_minutes: Number(e.target.value) })} className="rounded-xl border p-3" />
          <input placeholder="Descrição" value={service.description} onChange={(e: ChangeEvent<HTMLInputElement>) => setService({ ...service, description: e.target.value })} className="rounded-xl border p-3" />
        </div>
        <Button onClick={createService} className="mt-3 w-full">Cadastrar serviço</Button>
        <div className="mt-6 divide-y">
          {services.map(item => <div key={item.id} className="flex items-center justify-between gap-3 py-3 text-sm">
            <div><p className="font-semibold">{item.name}</p><p className="text-zinc-500">R$ {(item.price_cents / 100).toFixed(2).replace(".", ",")} · {item.duration_minutes} min · {item.is_active ? "ativo" : "inativo"}</p></div>
            <Button variant="secondary" onClick={() => toggleService(item)}>{item.is_active ? "Desativar" : "Ativar"}</Button>
          </div>)}
        </div>
      </section>
    </div>
  </div>;
}
