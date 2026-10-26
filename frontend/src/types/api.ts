export type Role = "user" | "barber" | "admin";

export interface User {
  id: string;
  email: string;
  role: Role;
  is_active: boolean;
}

export interface Service {
  id: string;
  name: string;
  description: string;
  price_cents: number;
  duration_minutes: number;
  is_active: boolean;
}

export interface Appointment {
  id: string;
  barber_id: string;
  client_id: string | null;
  service_id: string | null;
  starts_at: string;
  ends_at: string;
}

export interface Availability {
  date: string;
  service_id: string;
  service_duration_minutes: number;
  barbers: Array<{
    barber_id: string;
    email: string;
    slots: Array<{ starts_at: string; ends_at: string }>;
  }>;
}
