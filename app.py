from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


APP_TITLE = "간이 익명투표"
DB_PATH = Path(os.getenv("VOTE_DB_PATH", "data/votes.db"))
KST = timezone(timedelta(hours=9))
RAINBOW_COLORS = [
    ("빨강", "#EF4444"),
    ("주황", "#F97316"),
    ("노랑", "#EAB308"),
    ("초록", "#22C55E"),
    ("파랑", "#3B82F6"),
    ("남색", "#1D4ED8"),
    ("보라", "#A855F7"),
]
RAINBOW_COLOR_NAMES = [name for name, _ in RAINBOW_COLORS]
RAINBOW_COLOR_BY_NAME = dict(RAINBOW_COLORS)
RAINBOW_NAME_BY_COLOR = {color: name for name, color in RAINBOW_COLORS}
DEFAULT_COLOR = RAINBOW_COLORS[4][1]


st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🗳️",
    layout="centered",
    initial_sidebar_state="expanded",
)


def now_text() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with closing(get_connection()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agendas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                creator_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_open INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agenda_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                color TEXT NOT NULL DEFAULT '#3B82F6',
                sort_order INTEGER NOT NULL,
                FOREIGN KEY (agenda_id) REFERENCES agendas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agenda_id INTEGER NOT NULL,
                option_id INTEGER NOT NULL,
                voter_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (agenda_id) REFERENCES agendas(id) ON DELETE CASCADE,
                FOREIGN KEY (option_id) REFERENCES options(id) ON DELETE CASCADE,
                UNIQUE (agenda_id, voter_hash)
            );
            """
        )
        option_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(options)").fetchall()
        }
        if "color" not in option_columns:
            conn.execute(
                f"ALTER TABLE options ADD COLUMN color TEXT NOT NULL DEFAULT '{DEFAULT_COLOR}'"
            )
        conn.commit()


def normalize_voter_code(raw_code: str) -> str:
    return " ".join(raw_code.strip().split()).casefold()


def color_name_for_hex(color: str) -> str:
    return RAINBOW_NAME_BY_COLOR.get(color, color)


def clean_options(raw: str) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []

    for part in raw.replace(",", "\n").splitlines():
        label = " ".join(part.strip().split())
        key = label.casefold()
        if label and key not in seen:
            seen.add(key)
            cleaned.append(label)

    return cleaned


def create_agenda(
    title: str,
    description: str,
    option_labels: list[str],
    option_colors: list[str],
    voter_hash: str,
) -> int:
    with closing(get_connection()) as conn:
        cursor = conn.execute(
            """
            INSERT INTO agendas (title, description, creator_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (title, description, voter_hash, now_text()),
        )
        agenda_id = int(cursor.lastrowid)
        conn.executemany(
            """
            INSERT INTO options (agenda_id, label, color, sort_order)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    agenda_id,
                    label,
                    option_colors[index - 1]
                    if index - 1 < len(option_colors)
                    else DEFAULT_COLOR,
                    index,
                )
                for index, label in enumerate(option_labels, start=1)
            ],
        )
        conn.commit()
        return agenda_id


def list_agendas() -> list[sqlite3.Row]:
    with closing(get_connection()) as conn:
        return conn.execute(
            """
            SELECT
                a.id,
                a.title,
                a.description,
                a.created_at,
                a.creator_hash,
                COUNT(v.id) AS vote_count
            FROM agendas a
            LEFT JOIN votes v ON v.agenda_id = a.id
            WHERE a.is_open = 1
            GROUP BY a.id
            ORDER BY a.id DESC
            """
        ).fetchall()


def get_options(agenda_id: int) -> list[sqlite3.Row]:
    with closing(get_connection()) as conn:
        return conn.execute(
            """
            SELECT id, label, color
            FROM options
            WHERE agenda_id = ?
            ORDER BY sort_order, id
            """,
            (agenda_id,),
        ).fetchall()


def get_user_vote(agenda_id: int, voter_hash: str) -> sqlite3.Row | None:
    with closing(get_connection()) as conn:
        return conn.execute(
            """
            SELECT v.option_id, o.label, v.created_at
            FROM votes v
            JOIN options o ON o.id = v.option_id
            WHERE v.agenda_id = ? AND v.voter_hash = ?
            """,
            (agenda_id, voter_hash),
        ).fetchone()


def cast_vote(agenda_id: int, option_id: int, voter_hash: str) -> bool:
    with closing(get_connection()) as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO votes (agenda_id, option_id, voter_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (agenda_id, option_id, voter_hash, now_text()),
        )
        conn.commit()
        return cursor.rowcount == 1


def get_results(agenda_id: int) -> pd.DataFrame:
    with closing(get_connection()) as conn:
        rows = conn.execute(
            """
            SELECT
                o.label,
                o.color,
                COUNT(v.id) AS votes
            FROM options o
            LEFT JOIN votes v ON v.option_id = o.id
            WHERE o.agenda_id = ?
            GROUP BY o.id
            ORDER BY o.sort_order, o.id
            """,
            (agenda_id,),
        ).fetchall()

    df = pd.DataFrame([dict(row) for row in rows])
    if df.empty:
        return pd.DataFrame(columns=["선택지", "색상", "득표", "비율"])

    total = int(df["votes"].sum())
    df["ratio"] = 0.0 if total == 0 else df["votes"] / total
    df = df.rename(
        columns={"label": "선택지", "color": "색상", "votes": "득표", "ratio": "비율"}
    )
    return df


def render_results(agenda_id: int) -> None:
    df = get_results(agenda_id)
    total = int(df["득표"].sum()) if not df.empty else 0

    st.caption(f"총 {total}표")
    if total == 0:
        st.info("아직 집계된 표가 없어.")
        return

    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("선택지:N", sort=None, title=None),
            y=alt.Y("득표:Q", title="득표"),
            color=alt.Color(
                "선택지:N",
                scale=alt.Scale(
                    domain=df["선택지"].tolist(),
                    range=df["색상"].tolist(),
                ),
                legend=None,
            ),
            tooltip=["선택지:N", "득표:Q"],
        )
    )
    st.altair_chart(chart, use_container_width=True)

    display_df = df.copy()
    display_df["색상"] = display_df["색상"].map(color_name_for_hex)
    display_df["비율"] = display_df["비율"].map(lambda value: f"{value:.1%}")
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def render_create_form(voter_hash: str) -> None:
    st.subheader("의제 만들기")
    title = st.text_input("의제", placeholder="예: 다음 모임 날짜를 언제로 할까?")
    description = st.text_area(
        "설명",
        placeholder="필요하면 배경이나 조건을 적어줘.",
        height=90,
    )
    raw_options = st.text_area(
        "후보",
        value="찬성\n반대\n기권",
        help="줄바꿈이나 쉼표로 구분해. 최소 2개가 필요해.",
        height=110,
    )

    options = clean_options(raw_options)
    selected_colors: list[str] = []
    if options:
        st.caption("후보 색상")
        for index, label in enumerate(options):
            default_index = index % len(RAINBOW_COLORS)
            option_key = digest(f"{index}:{label}")[:10]
            color_column, preview_column = st.columns([3, 1])
            with color_column:
                color_name = st.selectbox(
                    label,
                    RAINBOW_COLOR_NAMES,
                    index=default_index,
                    key=f"color_{option_key}",
                )
            selected_color = RAINBOW_COLOR_BY_NAME[color_name]
            selected_colors.append(selected_color)
            with preview_column:
                st.markdown(
                    f"""
                    <div style="
                        width: 100%;
                        height: 2.35rem;
                        margin-top: 1.7rem;
                        border-radius: 6px;
                        background: {selected_color};
                        border: 1px solid rgba(0,0,0,.12);
                    "></div>
                    """,
                    unsafe_allow_html=True,
                )

    submitted = st.button("의제 올리기", type="primary")

    if not submitted:
        return

    if not title.strip():
        st.error("의제를 입력해줘.")
        return
    if len(options) < 2:
        st.error("후보는 최소 2개가 필요해.")
        return

    agenda_id = create_agenda(
        title.strip(),
        description.strip(),
        options,
        selected_colors,
        voter_hash,
    )
    st.success("의제를 올렸어. 이제 목록에서 투표할 수 있어.")
    st.session_state["selected_agenda_id"] = agenda_id
    st.rerun()


def render_agenda_card(agenda: sqlite3.Row, voter_hash: str) -> None:
    voted = get_user_vote(agenda["id"], voter_hash)
    options = get_options(agenda["id"])
    is_mine = agenda["creator_hash"] == voter_hash

    with st.container(border=True):
        heading = agenda["title"]
        if is_mine:
            heading += " · 내가 만든 의제"
        st.markdown(f"### {heading}")

        if agenda["description"]:
            st.write(agenda["description"])

        st.caption(f"생성: {agenda['created_at']} · 현재 투표 참여 {agenda['vote_count']}명")

        if voted:
            st.success(f"내 투표: {voted['label']}")
            render_results(agenda["id"])
            return

        labels_by_id = {row["id"]: row["label"] for row in options}
        selected_label = st.radio(
            "선택",
            list(labels_by_id.values()),
            key=f"option_{agenda['id']}",
            label_visibility="collapsed",
        )
        selected_id = next(
            option_id
            for option_id, label in labels_by_id.items()
            if label == selected_label
        )

        if st.button("투표하기", key=f"vote_{agenda['id']}", type="primary"):
            created = cast_vote(agenda["id"], selected_id, voter_hash)
            if created:
                st.success("투표했어. 바로 현황을 보여줄게.")
            else:
                st.info("이미 이 의제에 투표했어.")
            st.rerun()

        with st.expander("투표현황"):
            st.warning("투표를 마친 뒤에만 현황을 볼 수 있어.")


def render_agenda_list(voter_hash: str) -> None:
    st.subheader("진행 중인 의제")
    agendas = list_agendas()

    if not agendas:
        st.info("아직 의제가 없어. 첫 의제를 올려봐.")
        return

    for agenda in agendas:
        render_agenda_card(agenda, voter_hash)


def render_sidebar() -> str | None:
    st.sidebar.title(APP_TITLE)
    st.sidebar.caption("익명 투표 코드는 저장하지 않고 해시만 사용해.")
    raw_code = st.sidebar.text_input(
        "익명 투표 코드",
        type="password",
        placeholder="매번 같은 코드를 입력해줘",
        help="같은 코드를 쓰면 같은 사람으로 처리돼. DB에는 코드 원문이 저장되지 않아.",
    )

    voter_code = normalize_voter_code(raw_code)
    voter_hash = digest(f"voter-code:{voter_code}") if voter_code else None

    if voter_hash:
        st.sidebar.caption("현재 익명 ID")
        st.sidebar.code(voter_hash[:12], language=None)

    st.sidebar.divider()
    st.sidebar.write("투표 전에는 현황을 숨기고, 투표 후에는 바로 보여줘.")
    st.sidebar.write("같은 의제에는 같은 익명 코드로 한 번만 투표할 수 있어.")

    return voter_hash


def main() -> None:
    init_db()
    voter_hash = render_sidebar()

    st.title(APP_TITLE)
    st.write("누구나 의제를 만들고, 한 의제에는 같은 익명 코드로 한 번만 투표할 수 있어.")

    if voter_hash is None:
        st.info("왼쪽 사이드바에서 익명 투표 코드를 먼저 입력해줘.")
        st.stop()

    create_tab, vote_tab = st.tabs(["의제 만들기", "투표하기"])
    with create_tab:
        render_create_form(voter_hash)
    with vote_tab:
        render_agenda_list(voter_hash)


if __name__ == "__main__":
    main()
