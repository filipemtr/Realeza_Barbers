import { useEffect, useState } from "react";
import type { Appointment, Service } from "../types/api";
import { api } from "../services/api";
import { Button } from "../components/Button";

export function AppointmentsPage({ services, onBack }: { services: Service[]; onBack: () => void }) {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { api.appointments().then(setAppointments).catch(e => setError(e.message)); }, []);
  async function cancel(id: string) { if (!confirm("Cancelar este agendamento?")) return; try { await api.cancelAppointment(id); setAppointments(items => items.filter(item => item.id !== id)); } catch (e) { setError(e instanceof Error ? e.message : "Erro ao cancelar"); } }
  return <div className="mx-auto max-w-4xl"><button onClick={onBack} className="text-sm font-semibold text-zinc-500">← Voltar</button><h1 className="mt-3 text-4xl font-black">Meus agendamentos</h1>{error && <p className="mt-4 rounded-xl bg-red-50 p-3 text-red-700">{error}</p>}<div className="mt-7 space-y-3">{appointments.length === 0 ? <div className="rounded-2xl bg-white p-7 text-zinc-500">Você ainda não tem agendamentos.</div> : appointments.map(item => { const service = services.find(s => s.id === item.service_id); return <article key={item.id} className="flex flex-col gap-4 rounded-2xl bg-white p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between"><div><p className="font-bold">{service?.name ?? "Serviço"}</p><p className="mt-1 text-sm text-zinc-500">{new Date(item.starts_at).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" })}</p></div><Button variant="danger" onClick={() => cancel(item.id)}>Cancelar</Button></article>; })}</div></div>;
}
