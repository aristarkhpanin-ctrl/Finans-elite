import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Защита от одновременной правки держится на одной детали: сохранение **присылает**
 * ревизию той версии, которую правили (G2). Забудь её клиент — сервер вернётся к
 * прежней перезаписи, и правки коллеги снова исчезнут молча. Поэтому проверяется само
 * тело запроса, а не только то, что запрос ушёл.
 */

const put = vi.fn();
const post = vi.fn();
vi.mock("./client", async (orig) => ({
  ...(await orig<typeof import("./client")>()),
  api: { put: (...a: unknown[]) => put(...a), post: (...a: unknown[]) => post(...a) },
}));

const { updateProject, createProjectFromModel } = await import("./projects");
const { updateAuditSubject } = await import("./audit");

const model = { header: { name: "План", duration_months: 12 } } as never;

beforeEach(() => {
  put.mockReset().mockResolvedValue({ data: {} });
  post.mockReset().mockResolvedValue({ data: { id: "copy" } });
});

describe("сохранение присылает ревизию", () => {
  it("проект", async () => {
    await updateProject("p1", "План", model, "rev-1");
    expect(put).toHaveBeenCalledWith("/api/v1/projects/p1",
      { name: "План", model, expected_revision: "rev-1" });
  });

  it("дело", async () => {
    await updateAuditSubject("c1", "Дело", model, "rev-2");
    expect(put).toHaveBeenCalledWith("/api/v1/audit/subjects/c1",
      { name: "Дело", model, expected_revision: "rev-2" });
  });

  it("без ревизии поле не шлётся вовсе, а не шлётся пустым", async () => {
    // Пустая строка сравнилась бы с ревизией и дала ложный конфликт.
    await updateProject("p1", "План", model, "");
    expect(put.mock.calls[0][1]).not.toHaveProperty("expected_revision");
  });
});

it("копия с моими правками получает своё имя и в заголовке модели", async () => {
  // Имя проекта и имя в заголовке расходиться не должны: иначе следующее сохранение
  // копии молча переименовало бы её обратно.
  await createProjectFromModel("План — мои правки", model);
  const body = post.mock.calls[0][1] as { name: string; model: { header: { name: string } } };
  expect(body.name).toBe("План — мои правки");
  expect(body.model.header.name).toBe("План — мои правки");
});
