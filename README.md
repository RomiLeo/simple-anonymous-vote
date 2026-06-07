# 간이 익명투표

Streamlit Cloud에 바로 올릴 수 있는 간단한 익명투표 앱이야.

## 기능

- 누구나 의제를 만들 수 있음
- 선택지는 줄바꿈이나 쉼표로 입력
- 접속 URL에 저장된 익명 ID 기준으로 한 의제당 1회만 투표
- 투표 전에는 현황 숨김
- 투표 후에는 바로 집계 현황 표시

## 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud 배포

1. 이 폴더를 GitHub 저장소로 올림
2. Streamlit Cloud에서 새 앱 생성
3. main file path를 `app.py`로 지정

## 저장 방식

기본값은 `data/votes.db` SQLite 파일이야. 다른 경로를 쓰고 싶으면 환경변수로 지정하면 돼.

```bash
VOTE_DB_PATH=data/votes.db
```

익명 ID는 URL의 `voter` query parameter에 저장돼. 그래서 로그인 없는 간이 앱 특성상 URL 값을 지우거나 다른 주소로 새로 접속하는 것까지 완전히 막을 수는 없어.

Streamlit Cloud의 로컬 파일 저장소는 앱 재시작이나 재배포 때 초기화될 수 있어. 장기간 투표 데이터를 보존해야 하면 Supabase, PostgreSQL 같은 외부 DB로 바꾸는 게 좋아.
