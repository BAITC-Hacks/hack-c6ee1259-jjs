"""Readable jury demo built with native Streamlit components."""
from datetime import date
import streamlit as st
from ui.mock_data import PRESETS
from ui.service import get_recommendations


def apply_preset(index):
    for key, value in PRESETS[index].items():
        st.session_state[key] = value if key != "language" or value else "Не важно"
    st.session_state.pop("results", None)


def render_result(result):
    q = result["request"]
    st.subheader(q["date"])
    st.caption(f"{q['city']} · {q['event_type']} · {q['category']} · {q['budget']:,} ₸ · "
               f"{str(q['duration']) + ' ч' if q['duration'] else 'длительность не задана'} · {q['language'] or 'любой язык'}")
    st.caption(f"Источник: {result['source']}")
    st.markdown("**Воронка отбора**")
    maximum = max(result["funnel"][0]["count"], 1)
    for index, step in enumerate(result["funnel"]):
        st.progress(step["count"] / maximum, text=f"{'↓ ' if index else ''}{step['label']}: {step['count']}")
    if result["status"] == "matched":
        st.success(f"matched — подобрано: {len(result['cards'])}")
        if len(result["cards"]) < 3:
            st.info(f"Только {len(result['cards'])} из {result['funnel'][0]['count']} кандидатов проходят все условия. "
                    "Выдача не дополняется неподходящими профилями; причины отсева приведены ниже.")
        for card in result["cards"]:
            with st.container(border=True):
                st.markdown(f"### {card['name']}")
                st.write(f"{', '.join(card['categories'])} · {card['city']}")
                st.markdown(f"**От {card['price']:,} ₸** · **Score: {card['score']:.2f}/100**")
                badges = []
                for flag, label in [("synthetic", "synthetic: синтетический"), ("city_imputed", "imputed: город"), ("price_imputed", "imputed: цена")]:
                    if card[flag]:
                        badges.append(f":orange-badge[{label}]")
                if badges:
                    st.markdown(" ".join(badges))
                st.write(card["explanation"])
                with st.expander("Evidence — факты для объяснения"):
                    st.json(card["evidence"])
    elif result["status"] == "category_absent":
        st.info(f"category_absent — в городе {q['city']} нет категории «{q['category']}» в текущем каталоге.")
        st.write("Попробуйте другой город или категорию. Для mock это означает отсутствие только во временных данных.")
    elif result["status"] == "no_eligible":
        st.warning("no_eligible — кандидаты есть, но ни один не проходит все условия.")
    if result["diagnostics"]:
        st.markdown("**Diagnostics — причины отсева**")
        st.caption("Каждый профиль учитывается один раз, на первом не пройденном этапе.")
        for item in result["diagnostics"]:
            st.write(f"• {item['reason']}: {item['count']} — {', '.join(item['names'])}")
    if result["suggestions"]:
        st.markdown("**Suggestions — что можно изменить**")
        for suggestion in result["suggestions"]:
            st.write(f"• {suggestion}")


def main():
    st.set_page_config(page_title="HackAlem AI", page_icon="🔎", layout="wide")
    st.title("HackAlem AI")
    st.write("Подбор до трёх подрядчиков с понятными причинами рекомендации.")
    st.warning("Демо на mock-данных. Все профили вымышлены; backend/core пока не подключён.")
    st.caption("Score в mock — доля свободного бюджета, а не оценка качества. Цена «от» требует уточнения.")
    if "city" not in st.session_state:
        apply_preset(0)
    st.markdown("**Demo presets** — выберите сценарий, затем нажмите «Подобрать».")
    for i, col in enumerate(st.columns(4)):
        col.button(f"Preset {i + 1}", on_click=apply_preset, args=(i,), use_container_width=True)
    with st.form("request_form"):
        left, right = st.columns(2)
        with left:
            st.selectbox("Город", ["Алматы", "Астана", "Зарубежье"], key="city")
            st.date_input("Дата", min_value=date(2026, 9, 23), max_value=date(2026, 12, 31), key="date")
            st.selectbox("Тип мероприятия", ["корпоратив", "свадьба", "той", "конференция", "юбилей", "день рождения"], key="event_type")
            st.selectbox("Категория подрядчика", ["Ведущий", "Флорист", "Декоратор", "Фотограф", "Банкетный зал", "Подарки и сувениры", "Ведущий церемонии", "Фото и видеобудки", "Отель", "Инструменталист"], key="category")
        with right:
            st.number_input("Бюджет, ₸", min_value=1, step=50000, key="budget")
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
        except Exception:
            st.error("Не удалось получить рекомендации. Попробуйте повторить запрос или проверьте подключение backend.")
    if "results" not in st.session_state:
        st.info("Заполните форму или выберите preset и нажмите «Подобрать».")
        return
    results = st.session_state.results
    st.divider()
    st.caption("Результаты последнего отправленного запроса; после изменения формы нажмите «Подобрать».")
    if len(results) == 2:
        st.info("Меняется только дата. Различия в выдаче связаны с календарём занятости; имена отсеянных видны в diagnostics.")
        for column, result in zip(st.columns(2), results):
            with column:
                render_result(result)
    else:
        render_result(results[0])
