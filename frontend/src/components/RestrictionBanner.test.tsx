// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import type { OrganizationMembership } from "../api/types";
import { RestrictionBanner } from "./RestrictionBanner";

/**
 * Баннер режима чтения и выгрузки (ADMIN-DECOMPOSITION.md, B2).
 *
 * Проверяется не вёрстка, а три обещания: без ограничения баннера нет вовсе; ограничение
 * **названо** вместе с выходом из него; и оно показывается по активному продукту, а не
 * пугает того, кто открыл оплаченный.
 */

const org = (restrictions: OrganizationMembership["restrictions"] = []) =>
  ({ id: "o1", name: "Орг", role: "owner", created_at: "2026-01-01T00:00:00Z",
     restrictions } as OrganizationMembership);

afterEach(cleanup);

it("молчит, пока организация работает как обычно", () => {
  const { container } = render(<RestrictionBanner org={org()} product="business" />);
  expect(container.textContent).toBe("");
});

it("молчит и когда организации нет вовсе (профиль ещё грузится)", () => {
  const { container } = render(<RestrictionBanner org={undefined} product="business" />);
  expect(container.textContent).toBe("");
});

it("называет причину и путь выхода — оба с сервера", () => {
  render(<RestrictionBanner product="business" org={org([{
    product: "business", kind: "unpaid", blocking: true,
    reason: "Подписка на «Финанс-Элит» не оплачена.",
    remedy: "Данные доступны для просмотра и выгрузки; чтобы снова заводить и править их, оплатите тариф.",
  }])} />);
  expect(screen.getByText(/Режим чтения и выгрузки/)).toBeTruthy();
  expect(screen.getByText(/не оплачена/)).toBeTruthy();
  expect(screen.getByText(/оплатите тариф/)).toBeTruthy();
});

it("не пугает оплаченным продуктом из-за долга по соседнему", () => {
  // Подписка своя у каждого продукта: просроченный «Аудит» не повод показывать баннер
  // тому, кто открыл «Элит».
  const { container } = render(<RestrictionBanner product="business" org={org([{
    product: "audit", kind: "unpaid", blocking: true,
    reason: "Подписка на «Финанс-Аудит» не оплачена.",
    remedy: "…",
  }])} />);
  expect(container.textContent).toBe("");
});

it("приостановку и неоплату не путает: разный выход — разный текст", () => {
  render(<RestrictionBanner product="audit" org={org([{
    product: "audit", kind: "suspended", blocking: true,
    reason: "Приостановлена оператором платформы: жалоба.",
    remedy: "Данные доступны для просмотра и выгрузки. Снять приостановку может только платформа — напишите в поддержку.",
  }])} />);
  expect(screen.getByText(/Организация приостановлена/)).toBeTruthy();
  expect(screen.getByText(/напишите в поддержку/)).toBeTruthy();
  expect(screen.queryByText(/оплатите/i)).toBeNull();
});

it("льготный срок предупреждает, а не отказывает", () => {
  // Организация ещё работает: раскрасить это как отказ значило бы напугать того, у кого
  // всё в порядке, а не показать вовсе — отнять запись без предупреждения.
  const { container } = render(<RestrictionBanner product="business" org={org([{
    product: "business", kind: "grace", blocking: false,
    reason: "Оплаченный период подписки на «Финанс-Элит» закончился.",
    remedy: "Работа продолжается ещё 11 дней; после этого останутся просмотр, расчёт и выгрузка. Оплатите тариф, чтобы не прерываться.",
  }])} />);
  expect(screen.getByText(/Оплаченный период закончился/)).toBeTruthy();
  expect(screen.getByText(/ещё 11 дней/)).toBeTruthy();
  // И это не «режим чтения и выгрузки» — он ещё не наступил.
  expect(screen.queryByText(/Режим чтения и выгрузки/)).toBeNull();
  expect(container.querySelector(".restr--warn")).toBeTruthy();
});

it("отличие берётся с сервера, а не угадывается по виду", () => {
  // `kind` растёт со временем; угадывание блокирующих видов по нему однажды отстанет.
  const { container } = render(<RestrictionBanner product="business" org={org([{
    product: "business", kind: "unpaid", blocking: true,
    reason: "Подписка на «Финанс-Элит» не оплачена.", remedy: "…",
  }])} />);
  expect(container.querySelector(".restr--warn")).toBeNull();
});
