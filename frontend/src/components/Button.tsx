import type { ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" };

export function Button({ variant = "primary", className = "", ...props }: Props) {
  const variants = {
    primary: "bg-violet-600 text-white hover:bg-violet-500",
    secondary: "bg-white text-neutral-900 border border-neutral-200 hover:bg-neutral-50",
    danger: "bg-red-600 text-white hover:bg-red-500",
  };
  return <button className={`rounded-xl px-4 py-2.5 font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`} {...props} />;
}
