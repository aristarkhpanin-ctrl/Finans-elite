import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { httpDetail } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { PRODUCTS, type Product } from "./product";
import { Button } from "./ui";

/**
 * «Посмотреть демо без регистрации» (L2) — одна кнопка на экран входа и на главную (L5):
 * обработчик со входом, переходом и причиной отказа живёт здесь, а не копией в каждой
 * странице. Показывать её стоит только там, где демо заведено (`capabilities.demo`) —
 * обещание, которое сервер не выполнит, хуже отсутствия кнопки.
 */
export function DemoEntry({ product, onError, disabled, block = true }: {
  product: Product;
  /** Причина отказа словами сервера; пустая строка — сбросить прежнюю. */
  onError: (message: string) => void;
  disabled?: boolean;
  block?: boolean;
}) {
  const { loginDemo } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  async function enter() {
    onError("");
    setBusy(true);
    try {
      await loginDemo();
      navigate(PRODUCTS[product].home);
    } catch (err: unknown) {
      onError(httpDetail(err) ?? "Демо сейчас недоступно. Попробуйте позже.");
      setBusy(false);
    }
  }

  return (
    <Button variant="ghost" block={block} onClick={enter} loading={busy} disabled={disabled}>
      Посмотреть демо без регистрации
    </Button>
  );
}
