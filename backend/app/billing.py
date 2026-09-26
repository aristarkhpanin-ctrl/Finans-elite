"""Биллинг: тариф организации, контроль квот и платёжный провайдер.

- Квоты тарифа проверяются при создании проекта/добавлении участника (превышение → 402).
- Смена тарифа: ручной провайдер (6.5a, мгновенно) или через платёж ЮKassa (6.5b).
  Провайдер выбирается по окружению (``YOOKASSA_SHOP_ID``/``YOOKASSA_SECRET_KEY``).
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from . import crud, mail
from .billing_period import lost_days, paid_period_end, period_start
from .db_models import Payment, Subscription
from .plans import UNIT_NAME, Plan, get_plan


def activate_paid_plan(db: Session, org_id: str, plan: Plan,
                       paid_at: datetime | None = None, months: int = 1) -> Subscription:
    """Включить тариф **по факту оплаты** — и начать отсчёт оплаченного периода.

    Одна дверь на **всех**, кто проводит оплату: ручной провайдер (разработка), ЮKassa,
    автопродление и оператор платформы, проводящий оплату по счёту (F1). Раньше каждый
    звал ``set_plan`` сам, и добавить срок пришлось бы в трёх местах — ровно так и
    появляются подписки, которые истекают у одних клиентов и не истекают у других.

    Начало периода — :func:`billing_period.period_start`: продление того же тарифа
    **продолжает** текущий период, а не отсчитывает новый от даты платежа (G5). До этого
    досрочная оплата съедала оставшиеся дни.

    Новый период — новый счёт попыток автопродления: неудачи прошлого конца периода к
    следующему не относятся. Причина прошлой неудачи стирается, только пока согласие
    живо: если автопродление выключено, она объясняет, **почему** оно выключено.
    """
    paid_at = paid_at or datetime.now(timezone.utc)
    current = crud.get_subscription(db, org_id, plan.product)
    start = period_start(current.plan_code if current else None,
                         current.current_period_end if current else None, plan, paid_at)
    end = paid_period_end(plan, start, months)
    sub = crud.set_plan(db, org_id, plan.code, status="active", product=plan.product,
                        period_end=end, paid=True)
    sub.renew_attempts = 0
    sub.renew_attempted_at = None
    if sub.auto_renew:
        sub.renew_error = ""
    db.commit()
    db.refresh(sub)
    return sub


# --- Сколько платить (G5) ---

#: Сколько месяцев можно оплатить в самообслуживании: помесячно и за год. Другой срок —
#: оплата по счёту через платформу, где его задаёт оператор (F1).
SELF_SERVICE_MONTHS = (1, 12)

#: Скидка за годовую оплату, в процентах. **Размер скидки — решение владельца, а не
#: кода**: по умолчанию её нет, и продукт не придумывает её за него.
DISCOUNT_ENV = "ANNUAL_DISCOUNT_PERCENT"

#: Выше этого скидка считается опечаткой («90» вместо «9»): отдать год почти даром из-за
#: одной цифры хуже, чем не дать скидки и сказать об этом на экране готовности.
MAX_DISCOUNT_PERCENT = 50


def _discount_setting() -> tuple[int, str | None]:
    """Скидка из окружения и почему она не применяется (``None`` — применяется)."""
    raw = os.getenv(DISCOUNT_ENV, "").strip()
    if not raw:
        return 0, None
    try:
        value = int(raw)
    except ValueError:
        return 0, f"{DISCOUNT_ENV}=«{raw}» — не целое число процентов; скидка не применяется"
    if not 0 <= value <= MAX_DISCOUNT_PERCENT:
        return 0, (f"{DISCOUNT_ENV}={value} — вне пределов 0–{MAX_DISCOUNT_PERCENT}; "
                   "скидка не применяется")
    return value, None


def annual_discount_percent() -> int:
    return _discount_setting()[0]


def discount_problem() -> str | None:
    """Почему скидка из окружения не применяется — для экрана готовности (G9)."""
    return _discount_setting()[1]


def checkout_amount(plan: Plan, months: int) -> int:
    """Сумма к оплате, руб. — **одна** на экран оплаты, провайдера и автопродление.

    Скидка — только за год: помесячная оплата идёт по цене прайса. Округление — до
    рубля, половина вверх; при ценах, кратных сотне, оно не срабатывает вовсе.
    """
    full = plan.price_rub * months
    discount = annual_discount_percent() if months >= 12 else 0
    return (full * (100 - discount) + 50) // 100


@dataclass
class Quote:
    """Что случится при оплате — **до** неё, теми же функциями, что и сама оплата.

    Экран оплаты не считает срок сам: вторая копия правила «продление продолжает
    период» однажды пообещала бы одну дату, а оплата поставила бы другую.
    """

    plan_code: str
    months: int
    amount_rub: int
    full_price_rub: int
    discount_percent: int
    starts_at: datetime
    ends_at: datetime | None
    #: Продолжает ли оплата текущий период (тот же тариф) — а не начинает новый.
    continues: bool
    #: Сколько оплаченных суток прежнего тарифа пропадёт (перерасчёта нет).
    lost_days: int


def quote(db: Session, org_id: str, plan: Plan, months: int,
          now: datetime | None = None) -> Quote:
    now = now or datetime.now(timezone.utc)
    current = crud.get_subscription(db, org_id, plan.product)
    current_plan = current.plan_code if current else None
    current_end = current.current_period_end if current else None
    start = period_start(current_plan, current_end, plan, now)
    full = plan.price_rub * months
    amount = checkout_amount(plan, months)
    return Quote(plan_code=plan.code, months=months, amount_rub=amount,
                 full_price_rub=full,
                 discount_percent=annual_discount_percent() if amount < full else 0,
                 starts_at=start, ends_at=paid_period_end(plan, start, months),
                 continues=start != now,
                 lost_days=lost_days(current_plan, current_end, plan, now))


# --- Автопродление: доступно ли (G5) ---

def auto_renew_unavailable(provider: PaymentProvider) -> str | None:
    """Почему автопродление нельзя включить на этой установке (``None`` — можно).

    Одна дверь на три вопроса: показать ли отметку согласия, принять ли её при оплате,
    списывать ли по ней. Отметка, которая ни к чему не приведёт, — обещание, которое
    продукт не выполнит.

    **Без почты автопродления нет**: деньги клиента не списываются без письма о
    предстоящем списании, а письмо не уйдёт. Включить почту — решение владельца
    установки; продукт его не принимает, но и не делает вид, что оно принято.
    """
    if not provider.saves_methods:
        return "Оплата в продукте не подключена — автопродлению нечем списывать."
    if not mail.mail_enabled():
        return ("Автопродление требует почты: деньги не списываются без письма о "
                "предстоящем списании, а почта на этой установке выключена.")
    return None


#: Что клиенту разрешено менять самому. Платный тариф выдаёт **платёж**, а не право
#: `billing.manage`: оно есть у владельца организации-клиента, и прямая смена была
#: способом взять «Корпоративный» бесплатно и навсегда (срок при ней не ставился вовсе).
#:
#: Уйти на бесплатный — по-прежнему его право и его решение: это отказ от услуги, а не
#: её получение. Квота при этом падает, и отказ на следующем сохранении объяснит себя
#: сам — как и у неплательщика.
def is_self_service(plan: Plan) -> bool:
    """Может ли клиент перейти на этот тариф сам, без оплаты."""
    return plan.price_rub <= 0 and not plan.price_on_request


def current_plan(db: Session, org_id: str, product: str = "business") -> Plan:
    """Действующий тариф организации по продукту (без подписки — тариф по умолчанию)."""
    sub = crud.get_subscription(db, org_id, product)
    return get_plan(sub.plan_code if sub else None, product)


#: Разделитель перехода в журнале — тот же, что у смены роли участника («было → стало»).
PLAN_CHANGE_ARROW = " → "


def plan_change_details(product: str, was: str, became: str) -> str:
    """Строка журнала о смене тарифа: ``«business: pro → free»``.

    **Запись и чтение — одной парой функций.** В `details` лежал один продукт, а новый
    тариф — в `entity_name`, и запись не отвечала на вопрос «с чего ушли»: отличить уход
    с платного («клиента потеряли») от переключения бесплатного на бесплатный было нечем.
    Отток считается по журналу (F8), и без прежнего тарифа его пришлось бы угадывать.

    Заодно это чинит и сам журнал: «сменил тариф на бесплатный» без прежнего значения —
    запись слабее, чем у смены роли, где «было → стало» стоит с самого начала.
    """
    return f"{product}: {was}{PLAN_CHANGE_ARROW}{became}"


def parse_plan_change(details: str) -> tuple[str, str, str] | None:
    """Разобрать строку обратно: ``(продукт, прежний тариф, новый)``.

    ``None`` — **прежний тариф не назван**: так записаны все смены до F8, где в `details`
    лежал один продукт. Считать их уходом значило бы гадать, а считать «не уходом» —
    врать: метрика называет их отдельным числом и в отток не берёт.
    """
    product, colon, rest = details.partition(":")
    was, arrow, became = rest.partition(PLAN_CHANGE_ARROW)
    if not colon or not arrow:
        return None
    return product.strip(), was.strip(), became.strip()


def is_paid_plan(code: str) -> bool:
    """Платный ли тариф. «По запросу» — **платный**: его условия согласуют вне продукта,
    но бесплатным он от этого не становится, и уход с него — такой же уход."""
    plan = get_plan(code)
    return plan.price_rub > 0 or plan.price_on_request


#: Чем меряется квота единиц у каждого продукта: проектами у «Элит», делами у «Аудита».
#:
#: **Одна карта на проверку и на показ.** Экран сводки (F7) считает «осталось» отсюда же,
#: чем отказывает создание: посчитай он сам, и однажды показал бы «осталось 2» там, где
#: сохранение уже отвечает 402, — а клиент пошёл бы в поддержку с двумя правдами сразу.
#: Перечень закрыт: продукт без своей меры роняет тест.
UNIT_COUNT: dict[str, Callable[[Session, str], int]] = {
    "business": crud.count_projects,
    "audit": crud.count_audit_subjects,
}


def units_used(db: Session, org_id: str, product: str) -> int:
    """Сколько единиц квоты израсходовано — тем же счётом, что и в проверке."""
    counter = UNIT_COUNT.get(product)
    return counter(db, org_id) if counter is not None else 0


def _ensure_unit_quota(db: Session, org_id: str, product: str, used: int) -> None:
    """Общая проверка квоты единиц продукта: проектов у «Элит», дел у «Аудита».

    Одна функция на оба продукта не ради краткости: разойдясь, две копии однажды дали
    бы разный ответ на один и тот же вопрос «можно ли завести ещё».
    """
    plan = current_plan(db, org_id, product)
    if plan.max_units is not None and used >= plan.max_units:
        unit = UNIT_NAME.get(product, "объектов")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Достигнут лимит {unit} тарифа «{plan.name}» ({plan.max_units}). "
                   f"Перейдите на более высокий тариф.",
        )


def ensure_project_quota(db: Session, org_id: str) -> None:
    _ensure_unit_quota(db, org_id, "business", units_used(db, org_id, "business"))


def ensure_case_quota(db: Session, org_id: str) -> None:
    """Квота дел «Финанс-Аудит».

    До этого дела не считались вовсе: ``ensure_project_quota`` смотрел только проекты,
    а создание дела квоту не вызывало — на любом тарифе, включая бесплатный, дел можно
    было завести сколько угодно.
    """
    _ensure_unit_quota(db, org_id, "audit", units_used(db, org_id, "audit"))


def ensure_member_quota(db: Session, org_id: str, product: str = "business") -> None:
    plan = current_plan(db, org_id, product)
    if plan.max_members is not None and crud.count_members(db, org_id) >= plan.max_members:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Достигнут лимит участников тарифа «{plan.name}» ({plan.max_members}). "
                   f"Перейдите на более высокий тариф.",
        )


@dataclass
class CheckoutResult:
    """Результат инициации смены тарифа."""

    activated: bool                 # тариф активирован сразу (ручной провайдер)
    payment_id: str | None = None
    confirmation_url: str | None = None  # ссылка на оплату (ЮKassa)


@dataclass
class ChargeResult:
    """Чем кончилось списание сохранённым способом (автопродление, G5).

    Четыре исхода, и ни один не сводится к другому: ``succeeded`` — деньги списаны;
    ``pending`` — провайдер ещё решает, итог придёт уведомлением; ``failed`` — отказ с
    причиной; ``unknown`` — провайдер не ответил, и **неизвестно**, прошло ли списание.
    Последний нельзя считать отказом: повтор мог бы взять деньги дважды.
    """

    status: str
    provider_payment_id: str | None = None
    #: Причина словами — для экрана, журнала и письма.
    reason: str = ""
    #: Способ оплаты больше не принимается (карта просрочена, разрешение отозвано):
    #: согласие гасится, повторять бессмысленно.
    method_unusable: bool = False


class PaymentProvider(ABC):
    """Абстракция платёжного провайдера (сменяемая реализация)."""

    #: Умеет ли провайдер списывать сохранённым способом без клиента (G5).
    saves_methods: bool = False

    @abstractmethod
    def start_checkout(self, db: Session, org_id: str, plan: Plan, return_url: str,
                       customer_email: str, *, months: int = 1,
                       auto_renew: bool = False) -> CheckoutResult:
        """Инициировать смену тарифа (сразу или через платёж)."""

    def charge_saved(self, db: Session, payment: Payment, plan: Plan, method_id: str,
                     customer_email: str) -> ChargeResult:
        """Списать ``payment`` сохранённым способом (автопродление)."""
        return ChargeResult(status="failed",
                            reason="провайдер не умеет списывать сохранённым способом")

    def handle_webhook(self, db: Session, event: dict) -> None:  # noqa: B027 — необязательный хук (провайдер переопределяет по желанию)
        """Обработать уведомление провайдера (по умолчанию — игнор)."""


class ManualPaymentProvider(PaymentProvider):
    """6.5a: смена тарифа без внешнего платежа (для разработки/тестов).

    Включает тариф **сразу и без денег** — поэтому в продакшене не выбирается никогда
    (см. :func:`_build_provider`). Автопродление он «списывает» так же — без денег, и
    способ оплаты называет это прямо: спутать его с настоящей картой нельзя.
    """

    saves_methods = True
    METHOD_ID = "manual"
    METHOD_TITLE = "тестовый способ (ручной провайдер, без денег)"

    def start_checkout(self, db: Session, org_id: str, plan: Plan, return_url: str,
                       customer_email: str, *, months: int = 1,
                       auto_renew: bool = False) -> CheckoutResult:
        sub = activate_paid_plan(db, org_id, plan, months=months)
        if auto_renew:
            crud.enable_auto_renew(db, sub, method_id=self.METHOD_ID,
                                   method_title=self.METHOD_TITLE, months=months,
                                   amount_rub=checkout_amount(plan, months))
        return CheckoutResult(activated=True)

    def charge_saved(self, db: Session, payment: Payment, plan: Plan, method_id: str,
                     customer_email: str) -> ChargeResult:
        return ChargeResult(status="succeeded")


#: Почему в продукте нельзя оплатить. Отказ называет выход: без него клиент, готовый
#: платить, упирается в «ошибку» и уходит — хотя оплата по счёту работает всегда.
PAYMENT_UNAVAILABLE = (
    "Оплата в продукте сейчас не подключена. Тариф можно получить оплатой по счёту: "
    "свяжитесь с платформой — назначение тарифа она сделает сама.")


class UnavailablePaymentProvider(PaymentProvider):
    """Оплата не настроена, а установка — боевая: отказать, а не выдать тариф даром.

    Раньше на этом месте стоял ручной провайдер: без ключей ЮKassa он выбирался при
    **любом** окружении, и в продакшене ``checkout`` включал платный тариф одним запросом
    и без денег — та же дыра, что закрыл F1 на прямой смене тарифа, только через другую
    дверь. Отказ здесь — fail-closed, как у ``JWT_SECRET``: забытая настройка не должна
    превращаться в бесплатный тариф.
    """

    def start_checkout(self, db: Session, org_id: str, plan: Plan, return_url: str,
                       customer_email: str, *, months: int = 1,
                       auto_renew: bool = False) -> CheckoutResult:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=PAYMENT_UNAVAILABLE)


def settle_payment(db: Session, payment: Payment, *, saved_method_id: str | None,
                   saved_method_title: str = "") -> Subscription:
    """Оплата, **подтверждённая провайдером**: тариф, срок и — по согласию — автопродление.

    Автопродление включается двумя ключами сразу: отметкой согласия на **этом** платеже
    (наша запись) и способом, который провайдер **подтвердил** сохранённым. Одного
    недостаточно: сохранённый без согласия способ — это чужая настройка магазина, а
    согласие без способа — обещание, которому нечем списывать. Во втором случае клиенту
    сказано, что автопродление не включилось и почему; прежнее согласие на тот же тариф,
    если было, остаётся — новый способ не сохранился, а старый никто не отзывал.
    """
    crud.mark_payment(db, payment, "succeeded")
    plan = get_plan(payment.plan_code)
    sub = activate_paid_plan(db, payment.organization_id, plan, months=payment.months)
    if payment.auto_renew_consent:
        if saved_method_id:
            crud.enable_auto_renew(db, sub, method_id=saved_method_id,
                                   method_title=saved_method_title or "способ оплаты",
                                   months=payment.months, amount_rub=payment.amount_rub)
        elif not sub.auto_renew:
            crud.decline_auto_renew(db, sub, "провайдер не сохранил способ оплаты, "
                                             "списывать нечем — включить автопродление "
                                             "можно следующей оплатой")
    return sub


def _build_provider(app_env: str | None = None, shop_id: str | None = None,
                    secret: str | None = None) -> PaymentProvider:
    """Выбрать провайдера по окружению.

    Ключи ЮKassa заданы → ЮKassa. Нет ключей: вне продакшена — ручной (разработка,
    тесты), в продакшене — **отказ** (:class:`UnavailablePaymentProvider`).
    """
    app_env = os.getenv("APP_ENV", "development") if app_env is None else app_env
    shop_id = os.getenv("YOOKASSA_SHOP_ID") if shop_id is None else shop_id
    secret = os.getenv("YOOKASSA_SECRET_KEY") if secret is None else secret
    if shop_id and secret:
        from .payments_yookassa import YooKassaClient, YooKassaPaymentProvider
        return YooKassaPaymentProvider(YooKassaClient(shop_id, secret))
    if app_env.strip().lower() == "production":
        return UnavailablePaymentProvider()
    return ManualPaymentProvider()


def provider_kind(p: PaymentProvider) -> str:
    """Какой провайдер принимает оплату — для экрана готовности установки (G9)."""
    if isinstance(p, UnavailablePaymentProvider):
        return "unavailable"
    if isinstance(p, ManualPaymentProvider):
        return "manual"
    return "yookassa"


# Текущий провайдер.
provider: PaymentProvider = _build_provider()


def get_payment_provider() -> PaymentProvider:
    """FastAPI-зависимость (переопределяемая в тестах)."""
    return provider
