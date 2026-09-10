// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { MethodologyResponse } from "../../api/review";
import { MethodologyTab } from "./MethodologyTab";

/**
 * Методические трактовки (SPEC §22, фаза D2). Проверяется то, ради чего экран и сделан:
 * незадействованная развилка **не прячется** и называет причину молчания, а
 * предварительность версии сказана словами, а не оставлена читателю на догадку.
 */

const getMethodology = vi.fn();
vi.mock("../../api/review", async (orig) => ({
  ...(await orig<typeof import("../../api/review")>()),
  getMethodology: (...a: unknown[]) => getMethodology(...a),
}));

const answer = (over: Partial<MethodologyResponse> = {}): MethodologyResponse => ({
  engine_version: "0.9.39",
  confirmed: false,
  note: "Версия расчётного ядра предварительная (0.x): трактовки не подтверждены.",
  engaged_count: 1,
  choices: [
    {
      id: "vat.basis", number: 2, title: "Момент признания НДС", spec: "SPEC §11",
      chosen: "По отгрузке: НДС начисляется в момент реализации.",
      controls: ["settings.vat_basis"], open_question: "НДС с авансов.",
      engaged: true, silent_because: "", evidence: { vat_rate: "0.20" },
    },
    {
      id: "fx.revaluation", number: 3, title: "Курсовая разница (I25)", spec: "SPEC §5",
      chosen: "Переоцениваются монетарные статьи.",
      controls: [], open_question: "Налог на курсовую разницу.",
      engaged: false,
      silent_because: "Валютных статей в модели нет: курсовая разница равна нулю.",
      evidence: { i25_total: "0" },
    },
  ],
  ...over,
} as MethodologyResponse);

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  getMethodology.mockResolvedValue(answer());
});

function show() {
  render(
    <QueryClientProvider client={new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })}>
      <MethodologyTab projectId="p1" />
    </QueryClientProvider>,
  );
}

it("называет предварительность версии словами, а не оставляет на догадку", async () => {
  show();
  expect(await screen.findByText(/предварительная версия/)).toBeTruthy();
  expect(screen.getByText(/не подтверждены/)).toBeTruthy();
});

it("считает задействованные развилки и говорит, сколько их всего", async () => {
  show();
  // «Задействовано 1 из 2» — без знаменателя читатель не поймёт, что часть вопросов
  // к его модели просто не относится.
  expect(await screen.findByText(/из 2/)).toBeTruthy();
});

it("незадействованная развилка не прячется и называет причину молчания", async () => {
  show();
  // Спрятанный пункт читается как несуществующий, а он существует — просто здесь
  // не возникает.
  expect(await screen.findByText("Курсовая разница (I25)")).toBeTruthy();
  expect(screen.getByText(/Валютных статей в модели нет/)).toBeTruthy();
  expect(screen.getByText(/не возникают \(1\)/)).toBeTruthy();
});

it("у каждой развилки видно, что осталось несогласованным", async () => {
  show();
  expect(await screen.findByText(/НДС с авансов/)).toBeTruthy();
  expect(screen.getByText(/Налог на курсовую разницу/)).toBeTruthy();
});

it("несчитающийся проект не изображает пустую методику", async () => {
  // Пустой экран читался бы как «развилок нет», а на деле нет расчёта.
  getMethodology.mockRejectedValue(new Error("422"));
  show();
  expect(await screen.findByText(/проект не считается/)).toBeTruthy();
});
