import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const ru = {
  translation: {
    app: { title: "Финансовая модель" },
    auth: {
      login: "Вход",
      register: "Регистрация",
      email: "Email",
      password: "Пароль",
      fullName: "Имя",
      orgName: "Название организации",
      signIn: "Войти",
      signUp: "Зарегистрироваться",
      haveAccount: "Уже есть аккаунт? Войти",
      noAccount: "Нет аккаунта? Зарегистрироваться",
      invalid: "Неверный email или пароль",
      emailTaken: "Email уже зарегистрирован",
      genericError: "Что-то пошло не так. Попробуйте ещё раз.",
    },
    nav: { projects: "Проекты", logout: "Выйти" },
    projects: {
      title: "Проекты",
      empty: "Проектов пока нет",
      created: "создан",
    },
    common: { loading: "Загрузка…", theme: "Тема" },
  },
};

i18n.use(initReactI18next).init({
  resources: { ru },
  lng: "ru",
  fallbackLng: "ru",
  interpolation: { escapeValue: false },
});

export default i18n;
