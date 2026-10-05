// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { signedMoney } from "../format";
import { ReleaseNote } from "./ReleaseNote";

/**
 * Закрытие расчётов на конец горизонта (пакет K): оговорка с сервера и состав рядом с
 * показателями. Без расшифровки число последнего месяца читалось бы как выручка.
 */

afterEach(cleanup);

const release = {
  enabled: true,
  month: 11,
  total: "120441.48",
  note: "Показатели эффективности считаются с закрытием расчётов на конец горизонта.",
  items: [
    { code: "B2", label: "Счета к получению", amount: "120000.00" },
    { code: "B23", label: "Счета к оплате", amount: "-72000.00" },
  ],
};

describe("Закрытие расчётов под показателями", () => {
  it("печатает оговорку сервера и состав со знаками", () => {
    render(<ReleaseNote release={release} />);
    expect(screen.getByText(release.note)).toBeTruthy();
    const list = screen.getByRole("list", { name: "Состав закрытия расчётов" });
    expect(list.textContent).toContain("Счета к получению");
    expect(list.textContent).toContain(signedMoney("120000.00"));
    expect(list.textContent).toContain(signedMoney("-72000.00"));
  });

  it("выключенное закрытие не прячется: называет, что в показатели не вошло", () => {
    const off = { ...release, enabled: false, note: "Закрытие расчётов выключено." };
    render(<ReleaseNote release={off} />);
    expect(screen.getByText("Закрытие расчётов выключено.")).toBeTruthy();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("без закрытия (старый ответ) — ничего", () => {
    const { container } = render(<ReleaseNote release={null} />);
    expect(container.textContent).toBe("");
  });
});

describe("Деньги со знаком", () => {
  it("приход — с плюсом, уход — с типографским минусом, ноль — без знака", () => {
    expect(signedMoney("120000")).toMatch(/^\+120\s000\s₽$/);
    expect(signedMoney(-3000)).toMatch(/^−3\s000\s₽$/);
    expect(signedMoney(0)).toMatch(/^0\s₽$/);
    expect(signedMoney(null)).toBe("—");
  });
});
