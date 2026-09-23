"""Readable jury demo built with native Streamlit components."""
from datetime import date
import streamlit as st
from ui.presets import PRESETS
from ui.service import get_recommendations


def apply_preset(index):
    for key, value in PRESETS[index].items():
        st.session_state[key] = value if key != "language" or value else "Не важно"
    st.session_state.pop("results", None)


def render_result(result):
    q = result["request"]
    recommendations = result["recommendations"]
    diagnostics = result["diagnostics"]
    st.subheader(q["date"])
    st.caption(f"{q['city']} · {q['event_type']} · {q['category']} · {q['budget']:,} ₸ · "
               f"{str(q['duration']) + ' ч' if q['duration'] else 'длительность не задана'} · {q['language'] or 'любой язык'}")
    st.markdown("**Воронка отбора**")
    # Core counts the first failed filter; subtraction only formats its diagnostics.
    free = diagnostics["candidates"] - diagnostics["busy"]
    format_ok = free - diagnostics["format"]
    budget_ok = format_ok - diagnostics["budget"]
    funnel = [
        ("Кандидаты", diagnostics["candidates"]),
        ("Свободны на дату", free),
        ("Подходят по формату", format_ok),
        ("Проходят бюджет", budget_ok),
        ("Проходят язык/длительность", diagnostics["remaining"]),
        ("Рекомендованы", len(recommendations)),
    ]
    maximum = max(diagnostics["candidates"], 1)
    for index, (label, count) in enumerate(funnel):
        st.progress(count / maximum, text=f"{'↓ ' if index else ''}{label}: {count}")
    if result["status"] == "matched":
        st.success(f"matched — подобрано: {len(recommendations)}")
        if len(recommendations) < 3:
            st.info(f"Только {diagnostics['remaining']} из {diagnostics['candidates']} кандидатов проходят все условия. "
                    "Выдача не дополняется неподходящими профилями; причины отсева приведены ниже.")
        for card in recommendations:
            with st.container(border=True):
                st.markdown(f"### {card['name']}")
                st.write(f"{card['category']} · {card['city']}")
                st.markdown(f"**От {card['price_from_kzt']:,.0f} ₸** · **Score: {card['score']:.4f}/1**")
                badges = []
                for flag, label in [("synthetic", "synthetic: синтетический"), ("city_imputed", "imputed: город"), ("price_imputed", "imputed: цена")]:
                    # Optional CSV flags may arrive as strings, including 'false'.
                    if str(card.get(flag, False)).strip().casefold() in {"true", "1", "yes"}:
                        badges.append(f":orange-badge[{label}]")
                if badges:
                    st.markdown(" ".join(badges))
                st.write(card["explanation"])
                with st.expander("Evidence — факты для объяснения"):
                    st.json({key: value for key, value in card.items() if key != "explanation"})
    elif result["status"] == "category_absent":
        st.info(f"category_absent — в городе {q['city']} нет категории «{q['category']}» в текущем каталоге.")
        st.write("Попробуйте другой город или категорию.")
    elif result["status"] == "no_eligible":
        st.warning("no_eligible — кандидаты есть, но ни один не проходит все условия.")
    reasons = [
        ("busy", "Заняты на выбранную дату", "Попробуйте другую дату."),
        ("format", "Не работают с этим форматом", "Проверьте формат мероприятия."),
        ("budget", "Цена выше бюджета", "Рассмотрите увеличение бюджета."),
        ("language", "Не подходит язык", "Проверьте требуемый язык."),
        ("duration", "Превышена максимальная длительность", "Рассмотрите меньшую длительность, если это допустимо."),
    ]
    st.markdown("**Diagnostics — причины отсева**")
    st.caption("Каждый профиль учитывается один раз, на первом не пройденном этапе.")
    rejected = [(label, diagnostics[key], suggestion) for key, label, suggestion in reasons if diagnostics[key]]
    for label, count, _ in rejected:
        st.write(f"• {label}: {count}")
    if not rejected:
        st.caption("Отсев по условиям не зафиксирован.")
    with st.expander("Исходные diagnostics core"):
        st.json(diagnostics)
    if rejected:
        st.markdown("**Suggestions — что можно изменить**")
        for _, _, suggestion in rejected:
            st.write(f"• {suggestion}")


def main():
    st.set_page_config(page_title="HackAlem AI", page_icon="🔎", layout="wide")
    st.title("HackAlem AI")
    st.write("Подбор до трёх подрядчиков с понятными причинами рекомендации.")
    st.caption("Порядок, score и объяснения рассчитаны recommendation engine. Цена «от» требует уточнения.")
    # Discard results retained by Streamlit from an older mock UI session.
    if "results" in st.session_state and any("recommendations" not in r for r in st.session_state.results):
        st.session_state.pop("results", None)
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
            st.error("Каталог подрядчиков не найден. Core ожидает data/contractors.csv; передайте файл каталога участнику, отвечающему за данные.")
        except ValueError as error:
            st.error(f"Core не смог обработать параметры или каталог: {error}")
        except Exception:
            st.error("Не удалось получить рекомендации. Попробуйте повторить запрос или проверьте подключение backend.")
    if "results" not in st.session_state:
        st.info("Заполните форму или выберите preset и нажмите «Подобрать».")
        return
    results = st.session_state.results
    st.divider()
    st.caption("Результаты последнего отправленного запроса; после изменения формы нажмите «Подобрать».")
    if len(results) == 2:
        st.info("Меняется только дата. Выполнены два независимых запроса к core; diagnostics показывают число занятых кандидатов для каждой даты.")
        for column, result in zip(st.columns(2), results):
            with column:
                render_result(result)
    else:
        render_result(results[0])
