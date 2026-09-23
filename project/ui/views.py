"""Readable jury demo built with native Streamlit components."""
import streamlit as st
from ui.presets import PRESETS
from ui.presentation import explanation, human_date, money, short_result_message
from ui.service import DATASET_START, DATASET_END, get_recommendations

PRESET_LABELS = ("Плотная категория", "Редкая категория", "Недостаточный бюджет", "Категории нет")


def apply_preset(index):
    for key, value in PRESETS[index].items():
        st.session_state[key] = value if key != "language" or value else "Не важно"
    st.session_state["compare"] = False
    st.session_state.pop("results", None)


def render_result(result):
    q = result["request"]
    recommendations = result["recommendations"]
    diagnostics = result["diagnostics"]
    st.subheader(human_date(q["date"]))
    st.caption(f"{q['city']} · {q['event_type']} · {q['category']} · {money(q['budget'])} · "
               f"{str(q['duration']) + ' ч' if q['duration'] else 'длительность не задана'} · {q['language'] or 'любой язык'}")
    st.markdown("**Воронка отбора**")
    # Core counts the first failed filter; subtraction only formats its diagnostics.
    free = diagnostics["candidates"] - diagnostics["busy"]
    format_ok = free - diagnostics["format"]
    budget_ok = format_ok - diagnostics["budget"]
    funnel = [
        ("Кандидаты в городе и категории", diagnostics["candidates"]),
        ("Свободны на дату", free),
        ("Работают с этим форматом", format_ok),
        ("Укладываются в бюджет", budget_ok),
        ("Подходят по языку и длительности", diagnostics["remaining"]),
        ("Рекомендованы", len(recommendations)),
    ]
    maximum = max(diagnostics["candidates"], 1)
    for index, (label, count) in enumerate(funnel):
        st.progress(count / maximum, text=f"{'↓ ' if index else ''}{label}: {count}")
    if result["status"] == "matched":
        st.success(f"Подобрано: {len(recommendations)}")
        if len(recommendations) < 3:
            st.info(short_result_message(len(recommendations), diagnostics))
        for card in recommendations:
            with st.container(border=True):
                st.markdown(f"### {card['anon_name']}")
                st.write(f"{', '.join(card['categories'])} · {card['city']}")
                st.markdown(f"**От {money(card['price_from_kzt'])}**")
                badges = []
                for flag, label in [("synthetic", "Синтетический профиль"),
                                    ("price_imputed", "Цена восстановлена"),
                                    ("city_imputed", "Город восстановлен")]:
                    # Optional CSV flags may arrive as strings, including 'false'.
                    if str(card.get(flag, False)).strip().casefold() in {"true", "1", "yes"}:
                        badges.append(f":orange-badge[{label}]")
                if badges:
                    st.markdown(" ".join(badges))
                st.write(explanation(card, q))
                with st.expander("Почему этот подрядчик"):
                    st.write(f"Свободен на выбранную дату: {human_date(q['date'])}.")
                    st.write(f"Форматы в профиле: {', '.join(card['event_formats'])}.")
                    st.write(f"Языки в профиле: {', '.join(card['languages']) or 'не указаны'}.")
                    st.write(f"Стартовая цена: {money(card['price_from_kzt'])}. Бюджет: {money(q['budget'])}.")
                    if card["max_hours"] is None:
                        st.write("Для этой категории ограничение по длительности не применяется.")
                    else:
                        st.write(f"Максимальная длительность: {card['max_hours']:g} ч.")
                    st.caption("Описание из профиля")
                    st.write(card["description"] or "Описание не указано.")
                with st.expander("Технические детали"):
                    st.caption("Балл ранжирования помогает упорядочить подходящие профили. "
                               "Он не является вероятностью или оценкой качества подрядчика.")
                    st.json({"ID": card["id"], "Балл ранжирования": card["score"],
                             "Сходство описания": card["score_components"]["semantic_similarity"],
                             "Соответствие бюджету": card["score_components"]["budget_fit"],
                             "Соответствие формату": card["score_components"]["format_relevance"]})
    elif result["status"] == "category_absent":
        st.info("В этом городе нет такой категории")
        st.write(f"В каталоге нет подрядчиков категории «{q['category']}» в городе {q['city']}. "
                 "Попробуйте другой город или категорию.")
    elif result["status"] == "no_eligible":
        st.warning("Никто не подходит под все условия")
        st.write("Кандидаты в городе и категории есть, но каждый не проходит хотя бы одно условие.")
    reasons = [
        ("busy", "Заняты на выбранную дату"),
        ("format", "Не работают с этим форматом"),
        ("budget", "Цена выше бюджета"),
        ("language", "Не подходит язык"),
        ("duration", "Превышена максимальная длительность"),
    ]
    st.markdown("**Почему остальные не подошли**")
    st.caption("Каждый профиль учитывается один раз, на первом не пройденном этапе.")
    rejected = [(label, diagnostics[key]) for key, label in reasons if diagnostics[key]]
    for label, count in rejected:
        st.write(f"• {label}: {count}")
    if not rejected:
        st.caption("Кандидатов для проверки нет." if not diagnostics["candidates"] else
                   "Все кандидаты прошли условия.")
    suggestions = result.get("suggestions", {})
    if result["status"] == "no_eligible" and suggestions:
        st.markdown("**Что можно изменить**")
        st.caption("Каждая подсказка проверена отдельно: остальные условия запроса сохраняются.")
        if "minimum_budget_kzt" in suggestions:
            st.info("Чтобы получить хотя бы один вариант, увеличьте бюджет минимум до "
                    f"{money(suggestions['minimum_budget_kzt'])}. "
                    f"Это на {money(suggestions['budget_increase_kzt'])} больше текущего бюджета.")
        if "next_available_date" in suggestions:
            st.info(f"Ближайшая дата с доступным вариантом: {suggestions['next_available_date']}.")


def main():
    st.set_page_config(page_title="HackAlem AI", page_icon="🔎", layout="wide")
    st.title("HackAlem AI")
    st.write("Подбор до трёх подрядчиков с понятными причинами рекомендации.")
    st.caption("Подбор по данным каталога. Стартовая цена требует уточнения у подрядчика.")
    with st.expander("Как работает подбор"):
        st.markdown("""1. Сначала применяются жёсткие ограничения: город, категория, дата, формат, бюджет, язык и длительность.
2. Неподходящие подрядчики не могут попасть в рекомендации даже при высоком балле ранжирования.
3. Оставшиеся кандидаты ранжируются детерминированно.
4. Объяснение строится только из данных профиля.
5. Один и тот же запрос при неизменном каталоге даёт тот же порядок.""")
    # Discard incompatible results retained from earlier application versions.
    if "results" in st.session_state and any("recommendations" not in r for r in st.session_state.results):
        st.session_state.pop("results", None)
    if "city" not in st.session_state:
        apply_preset(0)
    st.markdown("**Сценарии для демо** — выберите сценарий, затем нажмите «Подобрать».")
    for i, col in enumerate(st.columns(4)):
        col.button(PRESET_LABELS[i], on_click=apply_preset, args=(i,), use_container_width=True)
    with st.form("request_form"):
        left, right = st.columns(2)
        with left:
            st.selectbox("Город", ["Алматы", "Астана", "Зарубежье"], key="city")
            st.date_input("Дата", min_value=DATASET_START, max_value=DATASET_END, key="date")
            st.caption("Доступность проверяется по календарю датасета с 23 сентября по 31 декабря 2026.")
            st.selectbox("Тип мероприятия", ["корпоратив", "свадьба", "той", "конференция", "юбилей", "день рождения"], key="event_type")
            st.selectbox("Категория подрядчика", ["Ведущий", "Флорист", "Декоратор", "Фотограф", "Банкетный зал", "Подарки и сувениры", "Ведущий церемонии", "Фото и видеобудки", "Отель", "Инструменталист"], key="category")
        with right:
            st.number_input("Бюджет, ₸", min_value=0, step=50000, key="budget")
            st.number_input("Длительность, часов (опционально)", min_value=1, max_value=168, value=None, key="duration", placeholder="Не задана")
            st.selectbox("Язык (опционально)", ["Не важно", "русский", "казахский", "английский"], key="language")
            st.checkbox("Сравнить 2026-09-30 и 2026-10-29", key="compare")
            st.caption("В сравнении поле «Дата» заменяется двумя фиксированными датами; остальные параметры одинаковы.")
        submitted = st.form_submit_button("Подобрать", type="primary")
    if submitted:
        request = {key: st.session_state[key] for key in PRESETS[0]}
        request["date"] = request["date"].isoformat()
        request["language"] = None if request["language"] == "Не важно" else request["language"]
        dates = ["2026-09-30", "2026-10-29"] if st.session_state.compare else [request["date"]]
        st.session_state.pop("results", None)
        try:
            with st.spinner("Подбираем подрядчиков…"):
                st.session_state.results = [get_recommendations({**request, "date": d}) for d in dates]
        except FileNotFoundError:
            st.error("Каталог подрядчиков не найден. Для подбора нужен файл data/contractors.csv.")
        except ValueError as error:
            st.error(f"Не удалось обработать параметры или каталог: {error}")
        except Exception:
            st.error("Не удалось получить рекомендации. Попробуйте повторить запрос или проверьте каталог.")
    if "results" not in st.session_state:
        st.info("Заполните форму или выберите сценарий и нажмите «Подобрать».")
        return
    results = st.session_state.results
    st.divider()
    st.caption("Результаты последнего отправленного запроса; после изменения формы нажмите «Подобрать».")
    if len(results) == 2:
        st.info("Меняется только дата. Подбор выполнен отдельно для каждой даты; "
                "воронка показывает, сколько кандидатов свободны и проходят остальные условия.")
        for column, result in zip(st.columns(2), results):
            with column:
                render_result(result)
    else:
        render_result(results[0])
