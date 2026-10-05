import { plural } from "./format";

/*
 * Подписи цен тарифов — одни на вкладку «Тариф и оплата» и на публичную страницу
 * «Тарифы» (L5): посетитель до регистрации и клиент на оплате читают одни и те же слова,
 * и вторая копия разошлась бы с первой при первой же правке.
 */

/** Сумма в рублях: «2 900 ₽». */
export const rub = (n: number) => `${n.toLocaleString("ru-RU")} ₽`;

/** «1 месяц», «2 месяца», «12 месяцев». */
export const monthCount = (n: number) => `${n} ${plural(n, "месяц", "месяца", "месяцев")}`;

/**
 * Подарок за оплату года — словами владельца: «2 месяца в подарок». Сумму считает сервер
 * (цена × (12 − подарок)); экран только называет, сколько месяцев подарено.
 */
export const gift = (n: number) => `${monthCount(n)} в подарок`;

/** Цена тарифа. «По запросу» — не ноль: ноль на экране читается как «бесплатно». */
export const price = (p: { price_rub: number; price_on_request: boolean }) =>
  p.price_on_request ? "По запросу" : p.price_rub === 0 ? "Бесплатно" : rub(p.price_rub);

/** Квота тарифа словами: «до 50 проектов · до 25 участников»; ``None`` — без ограничения. */
export const quota = (p: { max_units?: number | null; unit_name?: string;
                           max_members?: number | null }) =>
  [p.max_units != null ? `до ${p.max_units} ${p.unit_name ?? "проектов"}` : `${p.unit_name ?? "проектов"} без ограничения`,
   p.max_members != null ? `до ${p.max_members} ${plural(p.max_members, "участника", "участников", "участников")}`
     : "участников без ограничения"].join(" · ");
