import { describe, expect, it } from "vitest";
import { activationKind } from "./legal";

/** Подпись экрана активации: приглашению нужна отметка согласия, сбросу пароля — нет. */

const jwt = (payload: object) =>
  "eyJhbGciOiJIUzI1NiJ9." + btoa(JSON.stringify(payload)).replace(/=+$/, "")
    .replace(/\+/g, "-").replace(/\//g, "_") + ".sig";

describe("вид ссылки активации", () => {
  it("сброс пароля узнаётся по токену", () => {
    expect(activationKind(jwt({ sub: "u1", typ: "reset", pw: "x" }))).toBe("reset");
  });

  it("приглашение — приглашение", () => {
    expect(activationKind(jwt({ sub: "u1", typ: "invite" }))).toBe("invite");
  });

  it("нечитаемое — приглашение: лишний раз спросить согласие безопаснее", () => {
    expect(activationKind("мусор")).toBe("invite");
    expect(activationKind("a.%%%.b")).toBe("invite");
  });
});
