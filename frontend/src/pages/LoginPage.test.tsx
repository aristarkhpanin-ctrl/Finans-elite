// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * «Посмотреть демо» на экране входа (L2): кнопка есть **только** там, где сервер сказал,
 * что демо заведено, — обещание, которое установка не выполнит, хуже её отсутствия.
 */

const caps = vi.fn();
const loginDemo = vi.fn();
const navigate = vi.fn();

vi.mock("../api/auth", () => ({
  getCapabilities: () => caps(),
  requestPasswordReset: vi.fn(),
}));
vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({ login: vi.fn(), loginDemo }),
}));
vi.mock("../components/CubeHero", () => ({ CubeHero: () => <div data-testid="cube" /> }));
vi.mock("react-router-dom", async (orig) => ({
  ...(await orig<typeof import("react-router-dom")>()),
  useNavigate: () => navigate,
}));

const { LoginPage } = await import("./LoginPage");

function show() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><LoginPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("Демо без регистрации на входе", () => {
  it("кнопки нет, пока сервер не сказал, что демо заведено", async () => {
    caps.mockResolvedValue({ mail: false, error_tracking: false, demo: false });
    show();
    await waitFor(() => expect(caps).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /Посмотреть демо/ })).toBeNull();
  });

  it("кнопка входит в демо и ведёт в рабочую область", async () => {
    caps.mockResolvedValue({ mail: false, error_tracking: false, demo: true });
    loginDemo.mockResolvedValue(undefined);
    show();
    fireEvent.click(await screen.findByRole("button", { name: /Посмотреть демо/ }));
    await waitFor(() => expect(loginDemo).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(navigate).toHaveBeenCalled());
  });
});
