"""Субъекты анализа (Финанс-Аудит, продукт №2): CRUD, изоляция арендатора, инвариант.

Только слой хранения/API — ядро первого продукта не затрагивается.
"""
from __future__ import annotations


def _model(*, balanced: bool = True):
    """Модель субъекта на 2 периода. balanced=False — актив ≠ пассив во 2-м периоде."""
    return {
        "name": "ООО «Пример»",
        "currency": "RUB",
        "industry": "Торговля",
        "periods": [{"label": "2023", "kind": "year"}, {"label": "2024", "kind": "year"}],
        "balance": {
            "A_FIXED": ["100", "120"],
            "A_INVENTORY": ["30", "35"],
            "A_RECEIVABLE": ["40", "45"],
            "A_CASH": ["30", "50"],          # актив: 200, 250
            "P_EQUITY": ["120", "150" if balanced else "999"],
            "P_LONG": ["30", "30"],
            "P_SHORT": ["50", "70"],         # пассив: 200, 250 (или 250→1099 при !balanced)
        },
        "income": {
            "I_REVENUE": ["500", "600"],
            "I_COGS": ["300", "360"],
            "I_OPEX": ["80", "90"],
            "I_INTEREST": ["10", "12"],
            "I_OTHER": ["0", "0"],
            "I_TAX": ["22", "28"],
        },
    }


def _create(client, headers, **kw):
    return client.post("/api/v1/audit/subjects",
                       json={"name": "ООО «Пример»", "model": _model(**kw)}, headers=headers)


def test_create_get_list_subject(client, auth_headers):
    r = _create(client, auth_headers)
    assert r.status_code == 201
    sub = r.json()
    assert sub["n_periods"] == 2
    assert sub["balanced"] is True
    assert [str(x) for x in sub["balance_gap"]] == ["0", "0"]
    sid = sub["id"]

    got = client.get(f"/api/v1/audit/subjects/{sid}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["model"]["balance"]["A_FIXED"] == ["100", "120"]

    lst = client.get("/api/v1/audit/subjects", headers=auth_headers).json()
    assert len(lst) == 1 and lst[0]["id"] == sid and lst[0]["balanced"] is True


def test_unbalanced_flagged(client, auth_headers):
    sub = _create(client, auth_headers, balanced=False).json()
    assert sub["balanced"] is False
    # актив 2-го периода 250, пассив 250−150+999 = 1099 → разрыв 250−1099 = −849
    assert sub["balance_gap"][0] in ("0", 0)
    assert str(sub["balance_gap"][1]) == "-849"


def test_update_and_delete(client, auth_headers):
    sid = _create(client, auth_headers).json()["id"]
    upd = client.put(f"/api/v1/audit/subjects/{sid}",
                     json={"name": "Переименовано"}, headers=auth_headers)
    assert upd.status_code == 200 and upd.json()["name"] == "Переименовано"

    d = client.delete(f"/api/v1/audit/subjects/{sid}", headers=auth_headers)
    assert d.status_code == 204
    assert client.get(f"/api/v1/audit/subjects/{sid}", headers=auth_headers).status_code == 404


def test_tenant_isolation(client, register):
    a = register(email="a@e.ru", org="Орг A")
    b = register(email="b@e.ru", org="Орг B")
    sid = _create(client, a).json()["id"]
    # чужой субъект невидим и недоступен из другой организации
    assert client.get(f"/api/v1/audit/subjects/{sid}", headers=b).status_code == 404
    assert client.get("/api/v1/audit/subjects", headers=b).json() == []
    assert client.delete(f"/api/v1/audit/subjects/{sid}", headers=b).status_code == 404
    # владельцу — доступен
    assert client.get(f"/api/v1/audit/subjects/{sid}", headers=a).status_code == 200


def test_auth_required(client):
    assert client.get("/api/v1/audit/subjects").status_code in (401, 403)


def test_analyze_endpoint(client, auth_headers):
    """Анализ субъекта: аналитическая форма, тренды и коэффициенты по периодам."""
    sid = _create(client, auth_headers).json()["id"]
    r = client.post(f"/api/v1/audit/subjects/{sid}/analyze", headers=auth_headers)
    assert r.status_code == 200
    a = r.json()
    assert a["n"] == 2 and a["periods"] == ["2023", "2024"] and a["balanced"] is True

    # подытоги аналитической формы (актив 200/250, чистая прибыль 88/110)
    total = next(ln for ln in a["balance"] if ln["code"] == "A_TOTAL")
    assert [str(v) for v in total["values"]] == ["200", "250"] and total["subtotal"] is True
    net = next(ln for ln in a["income"] if ln["code"] == "I_NET")
    assert [str(v) for v in net["values"]] == ["88", "110"]

    # коэффициенты по группам присутствуют
    assert set(a["ratios"]) == {"liquidity", "activity", "gearing", "profitability"}
    assert str(a["ratios"]["liquidity"]["Коэффициент текущей ликвидности"][0]) == "2"

    # горизонтальный: первый период — база (null), далее Δ
    rev = next(t for t in a["horizontal"] if t["code"] == "I_REVENUE")
    assert rev["delta"][0] is None and str(rev["delta"][1]) == "100"


def test_analyze_isolated_and_missing(client, register):
    a = register(email="a2@e.ru", org="Орг A2")
    b = register(email="b2@e.ru", org="Орг B2")
    sid = _create(client, a).json()["id"]
    assert client.post(f"/api/v1/audit/subjects/{sid}/analyze", headers=b).status_code == 404
    assert client.post("/api/v1/audit/subjects/nope/analyze", headers=a).status_code == 404


# --- Карточка дела в списке и дубль (фаза 2 перехода на макеты) ---

def test_summary_carries_light_and_industry(client, auth_headers):
    """В списке дел видно состояние цели, а не только имя.

    Светофор считается по той же диагностике, что на вкладке дела: хранить его
    отдельно значило бы показывать результат, разошедшийся с отчётностью после
    первой же правки.
    """
    _create(client, auth_headers)
    row = client.get("/api/v1/audit/subjects", headers=auth_headers).json()[0]
    assert row["industry"] == "Торговля"
    assert row["light"] in {"ok", "warning", "risk"}

    # тот же светофор, что отдаёт анализ этого субъекта
    sid = row["id"]
    a = client.post(f"/api/v1/audit/subjects/{sid}/analyze", headers=auth_headers).json()
    assert row["light"] == a["diagnostics"]["light"]


def test_summary_light_absent_without_reporting(client, auth_headers):
    """Без отчётности светофор пуст, а не зелёный.

    «Не считалось» и «благополучно» — разные факты. Подставив ok, список показывал бы
    норму там, где данных просто не вводили.
    """
    empty = {"name": "", "currency": "RUB", "industry": "", "periods": [],
             "balance": {}, "income": {}}
    client.post("/api/v1/audit/subjects", json={"name": "Пустое", "model": empty},
                headers=auth_headers)
    row = next(r for r in client.get("/api/v1/audit/subjects",
                                     headers=auth_headers).json() if r["name"] == "Пустое")
    assert row["light"] is None and row["n_periods"] == 0


def test_duplicate_subject(client, auth_headers):
    """Дубль дела: модель целиком, имя с пометкой; оригинал не тронут."""
    sid = _create(client, auth_headers).json()["id"]
    r = client.post(f"/api/v1/audit/subjects/{sid}/duplicate", headers=auth_headers)
    assert r.status_code == 201
    copy = r.json()
    assert copy["id"] != sid
    assert copy["name"] == "ООО «Пример» (копия)"
    assert copy["model"] == client.get(f"/api/v1/audit/subjects/{sid}",
                                       headers=auth_headers).json()["model"]

    # оригинал на месте, в списке оба
    names = {s["name"] for s in client.get("/api/v1/audit/subjects",
                                           headers=auth_headers).json()}
    assert {"ООО «Пример»", "ООО «Пример» (копия)"} <= names


def test_duplicate_is_independent(client, auth_headers):
    """Копия — самостоятельное дело: правка копии не задевает оригинал."""
    sid = _create(client, auth_headers).json()["id"]
    cid = client.post(f"/api/v1/audit/subjects/{sid}/duplicate",
                      headers=auth_headers).json()["id"]
    client.put(f"/api/v1/audit/subjects/{cid}", json={"name": "Другое"},
               headers=auth_headers)
    assert client.get(f"/api/v1/audit/subjects/{sid}",
                      headers=auth_headers).json()["name"] == "ООО «Пример»"


def test_duplicate_isolated_and_missing(client, register):
    a = register(email="a3@e.ru", org="Орг A3")
    b = register(email="b3@e.ru", org="Орг B3")
    sid = _create(client, a).json()["id"]
    assert client.post(f"/api/v1/audit/subjects/{sid}/duplicate", headers=b).status_code == 404
    assert client.post("/api/v1/audit/subjects/nope/duplicate", headers=a).status_code == 404


def test_analyze_carries_input_issues(client, auth_headers):
    """Ответ анализа несёт находки о качестве ввода — «Экран 19».

    Находки считаются по исходной модели, а не по результату: анализ уже применил
    переоценки, а претензии предъявляются к тому, что ввели.
    """
    sid = _create(client, auth_headers, balanced=False).json()["id"]
    a = client.post(f"/api/v1/audit/subjects/{sid}/analyze", headers=auth_headers).json()
    gap = next(i for i in a["input_issues"] if i["code"] == "balance_gap")
    assert gap["severity"] == "error" and gap["periods"] == [1]
    assert "2024" in gap["detail"]


def test_analyze_clean_model_has_no_input_issues(client, auth_headers):
    """На здоровой отчётности список находок пуст — линтер не шумит."""
    sid = _create(client, auth_headers).json()["id"]
    a = client.post(f"/api/v1/audit/subjects/{sid}/analyze", headers=auth_headers).json()
    assert a["input_issues"] == []


def test_demo_subject_is_a_normal_case(client, auth_headers):
    """Демо-дело — обычное дело, а не особый режим.

    Его можно открыть, проанализировать, дублировать и удалить теми же кнопками:
    отдельный режим «только для просмотра» пришлось бы тянуть через весь редактор
    ради экрана, который пользователь видит один раз.
    """
    r = client.post("/api/v1/audit/subjects/demo", headers=auth_headers)
    assert r.status_code == 201
    demo = r.json()
    assert "вымышленные данные" in demo["name"]
    assert demo["n_periods"] == 3 and demo["balanced"] is True

    # оно действительно считается: светофор и заключение на месте
    a = client.post(f"/api/v1/audit/subjects/{demo['id']}/analyze",
                    headers=auth_headers).json()
    assert a["diagnostics"]["light"] in {"ok", "warning", "risk"}
    assert a["opinion"]
    # и проходит проверку ввода чисто — демонстрировать ошибки данных незачем
    assert a["input_issues"] == []

    # удаляется как любое другое
    assert client.delete(f"/api/v1/audit/subjects/{demo['id']}",
                         headers=auth_headers).status_code == 204


def test_demo_marks_fiction_in_the_name(client, auth_headers):
    """Пометка о вымышленности — в имени, потому что имя едет с делом всюду.

    В список, в свод группы, в шапку DOCX-заключения. Флаг в базе читали бы только
    там, где не забыли, и однажды демонстрация ушла бы наружу как настоящая проверка.
    """
    demo = client.post("/api/v1/audit/subjects/demo", headers=auth_headers).json()
    row = next(s for s in client.get("/api/v1/audit/subjects",
                                     headers=auth_headers).json() if s["id"] == demo["id"])
    assert "Демо" in row["name"] and "вымышленные" in row["name"]

    docx = client.get(f"/api/v1/audit/subjects/{demo['id']}/report.docx",
                      headers=auth_headers)
    assert docx.status_code == 200 and len(docx.content) > 0


def test_demo_isolated_by_organization(client, register):
    a = register(email="a4@e.ru", org="Орг A4")
    b = register(email="b4@e.ru", org="Орг B4")
    demo = client.post("/api/v1/audit/subjects/demo", headers=a).json()
    assert client.get(f"/api/v1/audit/subjects/{demo['id']}", headers=b).status_code == 404
