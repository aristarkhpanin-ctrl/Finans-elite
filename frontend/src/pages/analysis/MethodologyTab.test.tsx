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

it("расхождение с нормой стоит отдельным блоком, а не строкой «открыто к сверке»", async () => {
  // В общем списке расхождение читается как «ещё обсуждается», а у него есть ответ.
  getMethodology.mockResolvedValue(answer({
    classification_note: "Разбиение и основания — предложение платформы, а не подтверждение.",
    divergence_count: 1,
    needs_human_count: 1,
    choices: [{
      id: "tax.loss_carryforward", number: 7, title: "Перенос убытков", spec: "SPEC §11",
      chosen: "Последовательный пул убытков уменьшает базу будущих периодов.",
      controls: [], open_question: "Стартовый налоговый убыток.", engaged: true,
      silent_because: "", evidence: {}, resolution: "citable",
      proposed_basis: "п. 2.1 ст. 283 НК РФ: не более 50% базы.",
      divergence: "Пул покрывает базу целиком, без ограничения в 50%.",
    }],
  } as Partial<MethodologyResponse>));
  show();

  expect(await screen.findByText(/Где расчёт расходится с нормой/)).toBeTruthy();
  expect(screen.getByText(/без ограничения в 50%/)).toBeTruthy();
  // Оговорка едет рядом: «предложена норма» без неё читается как «уже согласовано».
  expect(screen.getByText(/предложение платформы, а не подтверждение/)).toBeTruthy();
});

it("способ закрытия назван рядом с вопросом — это разный объём работы читателя", async () => {
  getMethodology.mockResolvedValue(answer({
    needs_human_count: 1,
    choices: [
      {
        id: "vat.basis", number: 2, title: "Момент признания НДС", spec: "SPEC §11",
        chosen: "По отгрузке.", controls: [], open_question: "Возврат переплаты.",
        engaged: true, silent_because: "", evidence: {}, resolution: "citable",
        proposed_basis: "ст. 176 НК РФ.", divergence: "",
      },
      {
        id: "ratios.averaging", number: 6, title: "База коэффициентов", spec: "SPEC §18",
        chosen: "Оборачиваемость — на средние.", controls: [],
        open_question: "Какие строки усреднять.", engaged: true, silent_because: "",
        evidence: {}, resolution: "judgement", proposed_basis: "", divergence: "",
      },
    ],
  } as Partial<MethodologyResponse>));
  show();

  expect(await screen.findByText("есть норма — проверить")).toBeTruthy();
  expect(screen.getByText("нужно суждение")).toBeTruthy();
  expect(screen.getByText(/ст\. 176 НК РФ/)).toBeTruthy();
  // И число, ради которого классификация затевалась, — в шапке.
  expect(screen.getByText(/профессионального суждения ждут/)).toBeTruthy();
});

it("без расхождений блока нет вовсе — пустая рамка читалась бы как «есть, но не показали»", async () => {
  show();
  await screen.findByText(/Момент признания НДС/);
  expect(screen.queryByText(/Где расчёт расходится с нормой/)).toBeNull();
});
