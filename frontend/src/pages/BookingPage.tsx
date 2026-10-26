import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import type { Availability, Service } from "../types/api";
import { api } from "../services/api";
import { Button } from "../components/Button";

export function BookingPage({ services, onDone }: { services: Service[]; onDone: () => void }) {
  const [serviceId, setServiceId] = useState(services[0]?.id ?? "");
  const [date, setDate] = useState(() => new Date(Date.now() + 86400000).toISOString().slice(0, 10));
  const [availability, setAvailability] = useState<Availability | null>(null);
  const [selected, setSelected] = useState<{ barberId: string; starts: string; ends: string } | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => { if (serviceId) api.availability(serviceId, date).then(setAvailability).catch(e => setMessage(e.message)); }, [serviceId, date]);
  const selectedService = useMemo(() => services.find(s => s.id === serviceId), [services, serviceId]);

  async function submit() {
    if (!selected) return;
    setLoading(true); setMessage("");
    try {
      await api.createAppointment({ barber_id: selected.barberId, service_id: serviceId, starts_at: selected.starts, ends_at: selected.ends, confirmed: true });
      setMessage("Agendamento criado com sucesso!"); setSelected(null);
      setTimeout(onDone, 700);
    } catch (e) { setMessage(e instanceof Error ? e.message : "Erro ao agendar"); } finally { setLoading(false); }
  }

  return <div className="mx-auto max-w-4xl"><button onClick={onDone} className="text-sm font-semibold text-zinc-500">← Voltar</button><h1 className="mt-3 text-4xl font-black">Novo agendamento</h1>
    <div className="mt-7 grid gap-5 md:grid-cols-2"><label className="rounded-2xl bg-white p-5 font-semibold">Serviço<select value={serviceId} onChange={(e: ChangeEvent<HTMLSelectElement>) => { setServiceId(e.target.value); setSelected(null); }} className="mt-2 w-full rounded-xl border border-zinc-200 p-3">{services.map(s => <option key={s.id} value={s.id}>{s.name} — R$ {(s.price_cents / 100).toFixed(2).replace(".", ",")}</option>)}</select>{selectedService && <p className="mt-2 text-xs text-zinc-500">Duração: {selectedService.duration_minutes} minutos</p>}</label>
    <label className="rounded-2xl bg-white p-5 font-semibold">Data<input type="date" value={date} min={new Date().toISOString().slice(0, 10)} onChange={(e: ChangeEvent<HTMLInputElement>) => { setDate(e.target.value); setSelected(null); }} className="mt-2 w-full rounded-xl border border-zinc-200 p-3" /></label></div>
    <section className="mt-5 rounded-2xl bg-white p-5"><h2 className="font-bold">Horários disponíveis</h2>{availability?.barbers.length === 0 && <p className="mt-4 text-zinc-500">Nenhum barbeiro cadastrado.</p>}{availability?.barbers.map(barber => <div key={barber.barber_id} className="mt-5"><p className="text-sm font-bold">{barber.email}</p><div className="mt-2 flex flex-wrap gap-2">{barber.slots.map(slot => <button key={slot.starts_at} onClick={() => setSelected({ barberId: barber.barber_id, starts: slot.starts_at, ends: slot.ends_at })} className={`rounded-lg border px-3 py-2 text-sm font-semibold ${selected?.starts === slot.starts_at && selected?.barberId === barber.barber_id ? "border-neutral-900 bg-neutral-900 text-white" : "border-zinc-200 bg-zinc-50"}`}>{new Date(slot.starts_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" })}</button>)}</div></div>)}</section>
    {message && <p className="mt-4 rounded-xl bg-zinc-200 p-3 text-sm">{message}</p>}
    <Button disabled={!selected || loading} onClick={submit} className="mt-5 w-full">{loading ? "Confirmando..." : "Confirmar agendamento"}</Button>
  </div>;
}
