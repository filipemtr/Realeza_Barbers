import type { Appointment, Availability, Service, User } from "../types/api";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
  });

  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof data.detail === "string" ? data.detail : "Não foi possível concluir a operação.";
    throw new Error(message);
  }
  return data as T;
}

export const api = {
  me: () => request<User>("/auth/me"),
  login: (email: string, password: string) => request<{ message: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string) => request<{ message: string }>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  services: () => request<Service[]>("/services"),
  createService: (payload: Omit<Service, "id" | "is_active">) => request<Service>("/services", { method: "POST", body: JSON.stringify({ ...payload, is_active: true }) }),
  updateService: (id: string, payload: Omit<Service, "id" | "is_active"> & { is_active: boolean }) => request<Service>(`/services/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteService: (id: string) => request<void>(`/services/${id}`, { method: "DELETE" }),
  appointments: () => request<Appointment[]>("/appointments"),
  availability: (serviceId: string, date: string) => request<Availability>(`/availability?service_id=${encodeURIComponent(serviceId)}&date_value=${encodeURIComponent(date)}`),
  createAppointment: (payload: Record<string, unknown>) => request<Appointment>("/appointments", { method: "POST", body: JSON.stringify(payload) }),
  cancelAppointment: (id: string) => request<void>(`/appointments/${id}`, { method: "DELETE", body: JSON.stringify({ confirmed: true }) }),
  adminUsers: () => request<User[]>("/admin/users"),
  createUser: (payload: Record<string, unknown>) => request<User>("/admin/users", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (id: string, payload: Record<string, unknown>) => request<User>(`/admin/users/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteUser: (id: string) => request<void>(`/admin/users/${id}`, { method: "DELETE" }),
};
