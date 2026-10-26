import { useEffect, useState } from "react";
import type { Service, User } from "../types/api";
import { Button } from "../components/Button";
import { BrandMark } from "../components/BrandMark";

const experiences = [
  { quote: "Seu horário organizado em poucos cliques, sem depender de longas trocas de mensagens.", name: "Agendamento sem complicação", detail: "Mais praticidade no seu dia" },
  { quote: "Um atendimento preparado para valorizar seu estilo e respeitar o seu tempo.", name: "Cuidado em cada detalhe", detail: "Experiência Realeza" },
  { quote: "Escolha o serviço que combina com você e chegue sabendo que seu momento está reservado.", name: "Seu estilo, no seu tempo", detail: "Do clique ao atendimento" },
];

const formatPrice = (priceCents: number) => (priceCents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

type Props = { user: User | null; services: Service[]; onBook: () => void; onLogin: () => void; onRegister: () => void; onAppointments: () => void; onAdmin: () => void };

export function HomePage({ user, services, onBook, onLogin, onRegister, onAppointments, onAdmin }: Props) {
  const [testimonialIndex, setTestimonialIndex] = useState(0);
  const activeServices = services.filter(service => service.is_active);
  const featuredServices = activeServices.slice(0, 3);
  const [timeLabel, setTimeLabel] = useState("");

  useEffect(() => {
    const updateLabel = () => setTimeLabel(new Intl.DateTimeFormat("pt-BR", { weekday: "long", hour: "2-digit", minute: "2-digit" }).format(new Date()));
    updateLabel();
    const clock = window.setInterval(updateLabel, 60_000);
    const carousel = window.setInterval(() => setTestimonialIndex(current => (current + 1) % experiences.length), 6500);
    return () => { window.clearInterval(clock); window.clearInterval(carousel); };
  }, []);

  const mainAction = user ? onBook : onRegister;
  const mainLabel = user ? "Reservar meu horário" : "Agendar agora";

  return <div className="landing-page">
    <section className="hero-section">
      <div className="hero-glow hero-glow-one" aria-hidden="true" />
      <div className="hero-glow hero-glow-two" aria-hidden="true" />
      <div className="hero-copy reveal-up">
        <div className="availability-pill"><span className="status-dot" /> EXPERIÊNCIA PREMIUM <span className="pill-divider" /> <span className="live-time">{timeLabel || "Seu estilo, no seu tempo"}</span></div>
        <p className="hero-kicker">MAIS QUE UM CORTE. UMA ASSINATURA.</p>
        <h1>Seu estilo merece<br />entrar para a <span className="gradient-word">realeza.</span></h1>
        <p className="hero-description">Precisão nos detalhes. Presença em cada traço. Encontre seu próximo visual e reserve seu momento com quem entende de estilo.</p>
        <div className="hero-actions">
          <Button onClick={mainAction} className="!rounded-full !bg-violet-500 !px-7 !py-4 !text-white hover:!bg-violet-400">{mainLabel} <span aria-hidden="true" className="ml-2">↗</span></Button>
          {!user && <Button variant="secondary" onClick={onLogin} className="!rounded-full !border-white/20 !bg-white/5 !px-7 !py-4 !text-white hover:!bg-white/10">Já sou cliente</Button>}
          {user && <Button variant="secondary" onClick={onAppointments} className="!rounded-full !border-white/20 !bg-white/5 !px-7 !py-4 !text-white hover:!bg-white/10">Meus horários</Button>}
          {user?.role === "admin" && <Button variant="secondary" onClick={onAdmin} className="!rounded-full !border-white/20 !bg-white/5 !px-7 !py-4 !text-white hover:!bg-white/10">Painel admin</Button>}
        </div>
        <div className="hero-proof"><div className="avatar-stack" aria-hidden="true"><span><BrandMark title="" /></span><span>B</span><span>+</span></div><div><div className="proof-stars" aria-label="Experiência cinco estrelas">★★★★★</div><p>Estilo elevado. Atendimento de verdade.</p></div></div>
      </div>
      <div className="hero-visual reveal-up delay-2">
        <div className="hero-image-frame"><img src="https://images.unsplash.com/photo-1503951914875-452162b0f3f1?auto=format&fit=crop&w=1200&q=85" alt="Interior sofisticado de uma barbearia moderna" fetchPriority="high" /><div className="image-vignette" />
          <div className="image-caption"><span className="caption-mark"><BrandMark /></span><div><strong>O padrão Realeza</strong><span>Seu momento. Seu estilo.</span></div><span className="caption-arrow">↗</span></div>
        </div>
        <div className="floating-card floating-card-top"><span className="floating-icon">✦</span><div><strong>Detalhe é tudo.</strong><span>Precisão em cada corte</span></div></div>
        <div className="floating-card floating-card-bottom"><span className="mini-clock">◷</span><div><strong>Seu tempo importa</strong><span>Agendamento sem espera</span></div></div>
        <div className="hero-orbit" aria-hidden="true" />
      </div>
      <div className="hero-bottom-line"><span>ESTILO COM IDENTIDADE</span><span className="bottom-line-center" /><span>DESLIZE PARA DESCOBRIR ↓</span></div>
    </section>

    <section className="trust-strip" aria-label="Diferenciais Realeza"><div><span className="trust-icon">✦</span><p><strong>Atendimento premium</strong><span>Você no centro de tudo</span></p></div><div><span className="trust-icon">◷</span><p><strong>Horário reservado</strong><span>Mais praticidade no dia a dia</span></p></div><div><span className="trust-icon">✧</span><p><strong>Profissionais dedicados</strong><span>Cuidado do início ao fim</span></p></div></section>

    <section className="services-section" id="servicos">
      <div className="section-heading reveal-up"><div><p className="section-eyebrow">A CURADORIA REALEZA</p><h2>Seu próximo visual<br /><span>começa aqui.</span></h2></div><p className="section-intro">Escolha o serviço que combina com você. Nossa missão é transformar cuidado pessoal em uma experiência à altura do seu estilo.</p></div>
      {featuredServices.length > 0 ? <div className="service-grid">{featuredServices.map((service, index) => <article className={`service-card reveal-up delay-${index + 1}`} key={service.id}><div className="service-card-top"><span className="service-number">0{index + 1}</span><span className="service-symbol">{index === 0 ? "✦" : index === 1 ? "◈" : "✧"}</span></div><h3>{service.name}</h3><p>{service.description || "Técnica, cuidado e atenção aos detalhes em cada atendimento."}</p><div className="service-meta"><strong>{formatPrice(service.price_cents)}</strong><span>◷ {service.duration_minutes} min</span></div><button className="service-link" onClick={mainAction}>Escolher este serviço <span aria-hidden="true">↗</span></button></article>)}</div> : <div className="empty-services"><span>✦</span><strong>Estamos preparando a experiência.</strong><p>Os serviços serão exibidos aqui assim que estiverem disponíveis.</p></div>}
      {activeServices.length > 3 && <p className="more-services-note">+ {activeServices.length - 3} {activeServices.length - 3 === 1 ? "serviço disponível" : "serviços disponíveis"} no momento do agendamento.</p>}
    </section>

    <section className="experience-section"><div className="experience-art"><img src="https://images.unsplash.com/photo-1621605815971-fbc98d665033?auto=format&fit=crop&w=1000&q=85" alt="Barbeiro realizando acabamento com precisão" loading="lazy"/><div className="experience-art-overlay"/><div className="experience-stamp"><BrandMark /><small>FEITO COM<br/>PROPÓSITO</small></div></div><div className="experience-copy reveal-up"><p className="section-eyebrow">A EXPERIÊNCIA FAZ A DIFERENÇA</p><h2>O cuidado está<br />nos <span>detalhes.</span></h2><p>Uma boa barbearia não entrega só um corte. Entrega confiança, tempo bem aproveitado e a sensação de sair renovado.</p><div className="experience-points"><div><span>01</span><p><strong>Você escolhe</strong><small>Serviço e horário de um jeito simples.</small></p></div><div><span>02</span><p><strong>A gente se prepara</strong><small>Seu horário fica organizado com antecedência.</small></p></div><div><span>03</span><p><strong>Você chega no estilo</strong><small>Mais tempo para o que realmente importa.</small></p></div></div><Button onClick={mainAction} className="!mt-8 !rounded-full !bg-violet-500 !px-7 !py-3.5 !text-white hover:!bg-violet-400">{mainLabel} <span aria-hidden="true" className="ml-2">↗</span></Button></div></section>

    <section className="testimonial-section"><div className="testimonial-heading"><p className="section-eyebrow">O PADRÃO REALEZA</p><h2>Cada detalhe faz parte<br /><span>da experiência.</span></h2></div><div className="testimonial-card" aria-live="polite"><div className="testimonial-stars">✦ &nbsp; FEITO PARA VOCÊ</div><span className="quote-mark">“</span><blockquote>{experiences[testimonialIndex].quote}</blockquote><div className="testimonial-footer"><div className="testimonial-avatar">{experiences[testimonialIndex].name.charAt(0)}</div><div><strong>{experiences[testimonialIndex].name}</strong><span>{experiences[testimonialIndex].detail}</span></div><div className="testimonial-controls">{experiences.map((item, index) => <button key={item.name} aria-label={`Ver diferencial ${index + 1}`} aria-pressed={index === testimonialIndex} onClick={() => setTestimonialIndex(index)} className={index === testimonialIndex ? "active" : ""} />)}</div></div></div></section>

    <section className="final-cta"><div className="cta-orb" aria-hidden="true"/><p className="section-eyebrow">SEU PRÓXIMO CAPÍTULO COMEÇA AQUI</p><h2>Pronto para elevar<br />o seu <span>estilo?</span></h2><p>Reserve seu horário em poucos cliques. O seu momento Realeza está esperando.</p><Button onClick={mainAction} className="!rounded-full !bg-white !px-8 !py-4 !font-bold !text-zinc-950 hover:!bg-violet-100">{mainLabel} <span aria-hidden="true" className="ml-2">↗</span></Button><div className="cta-bottom"><span>REALEZA BARBERS</span><span>SEU ESTILO, SUA ASSINATURA.</span></div></section>
  </div>;
}
