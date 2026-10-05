import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { getCapabilities } from "../api/auth";
import { getToken } from "../api/client";
import { getPlans } from "../api/org";
import { DemoEntry } from "../components/DemoEntry";
import { PublicLayout } from "../components/PublicLayout";
import { PRODUCTS, type Product } from "../components/product";
import { usePageTitle } from "../pageTitle";
import { quota } from "../planText";
import { BRAND } from "./auth/AuthLayout";

/**
 * Главная (пакет L, L5) — для того, кто ещё не вошёл: что это за сервисы, сколько стоят и
 * кто их оказывает. Вошедшего она сразу ведёт в рабочую область — рекламировать продукт
 * его пользователю незачем.
 *
 * Описание продуктов — то же, что на панели экрана входа (`BRAND`): обещания в двух
 * местах однажды разошлись бы, и одно из них стало бы неправдой.
 */
export function HomePage() {
  usePageTitle("Финансовая модель и проверка отчётности");
  const { data: caps } = useQuery({ queryKey: ["capabilities"], queryFn: getCapabilities,
                                    staleTime: Infinity, enabled: !getToken() });
  const { data: plans } = useQuery({ queryKey: ["plans", "business"],
                                     queryFn: () => getPlans("business"), enabled: !getToken() });
  // Обещание про бесплатный тариф — из каталога, а не текстом: каталог меняется.
  const free = plans?.find((p) => p.price_rub === 0 && !p.price_on_request);
  const [demoError, setDemoError] = useState("");
  if (getToken()) return <Navigate to="/projects" replace />;

  return (
    <PublicLayout>
      <section className="pub-hero">
        <h1 className="pub-hero__title">
          Финансовая модель бизнеса и проверка фирмы-цели — в одном месте
        </h1>
        <p className="pub-hero__lead">
          Помесячный расчёт четырёх отчётов, показатели эффективности и оценка бизнеса; анализ
          фактической отчётности с реестром рисков. Каждый пробел в данных назван, а не
          заполнен догадкой.
        </p>
        <div className="pub-hero__actions">
          <Link to="/register" className="btn">Зарегистрироваться бесплатно</Link>
          {caps?.demo && <DemoEntry product="business" onError={setDemoError} block={false} />}
        </div>
        {demoError && <div className="field-note field-note--warn" role="alert">{demoError}</div>}
      </section>

      <div className="pub-products">
        {(["business", "audit"] as Product[]).map((key) => {
          const copy = BRAND[key];
          return (
            <section key={key} className="pub-product" aria-labelledby={`pub-${key}`}>
              <h2 id={`pub-${key}`} className="pub-product__name">
                Финанс{PRODUCTS[key].brand}
              </h2>
              <div className="pub-product__head">{copy.headline}</div>
              <p className="pub-product__lead">{copy.lead}</p>
              <ul className="pub-product__feats">
                {copy.features.map(([title, sub]) => (
                  <li key={title}><b>{title}</b><span>{sub}</span></li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>

      <section className="pub-more">
        <h2 className="rsection-label">Что важно знать до регистрации</h2>
        <ul className="pub-more__list">
          <li>
            {free
              ? `Тариф «${free.name}» бесплатный и без срока: ${quota(free)}. `
              : "Цены — на странице тарифов. "}
            <Link to="/pricing">Все тарифы</Link>
          </li>
          <li>
            Ваши данные — ваши: модели выгружаются целиком, организация удаляется вместе с
            ними, а сотрудники платформы содержимого моделей не видят.
          </li>
          <li>
            Методика открыта: трактовки, которые требуют профессионального суждения, и места,
            где расчёт расходится с нормой, названы в самом сервисе на вкладке «Методика».
          </li>
        </ul>
      </section>
    </PublicLayout>
  );
}
