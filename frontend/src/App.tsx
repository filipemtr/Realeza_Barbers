import { useEffect, useState } from "react";
import { Layout } from "./components/Layout";
import { api } from "./services/api";
import type { Service, User } from "./types/api";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { BookingPage } from "./pages/BookingPage";
import { AppointmentsPage } from "./pages/AppointmentsPage";
import { AdminPage } from "./pages/AdminPage";

type Page = "home" | "login" | "register" | "booking" | "appointments" | "admin";

export default function App() {
  const [user, setUser] = useState<User | null>(null); 
  const [services, setServices] = useState<Service[]>([]); 
  const [page, setPage] = useState<Page>("home"); 
  const [ready, setReady] = useState(false);

  useEffect(() => {
    Promise.allSettled([
      api.services().then(setServices),
      api.me().then(setUser),
    ]).finally(() => setReady(true));
  }, []);


  async function login(email: string, password: string) { await api.login(email, password); setUser(await api.me()); setPage("home"); }
  async function register(email: string, password: string) { await api.register(email, password); await login(email, password); }
  async function logout() { await api.logout(); setUser(null); setPage("home"); }

  if (!ready) return <div className="grid min-h-screen place-items-center bg-zinc-100">Carregando...</div>;

  return <Layout user={user} onLogout={logout} onHome={() => setPage("home")}>
    {page === "home" && <HomePage user={user} services={services} onBook={() => setPage("booking")} onLogin={() => setPage("login")} onRegister={() => setPage("register")} onAppointments={() => setPage("appointments")} onAdmin={() => setPage("admin")} />}
    {page === "login" && <LoginPage onLogin={login} onCreateAccount={() => setPage("register")} />}
    {page === "register" && <RegisterPage onRegister={register} onBackToLogin={() => setPage("login")} />}
    {page === "booking" && user && <BookingPage services={services} onDone={() => setPage("home")} />}
    {page === "appointments" && user && <AppointmentsPage services={services} onBack={() => setPage("home")} />}
    {page === "admin" && user?.role === "admin" && <AdminPage onBack={() => setPage("home")} />}
  </Layout>;
}
