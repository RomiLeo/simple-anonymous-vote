# 간이 익명투표

Streamlit Cloud에 바로 올릴 수 있는 간단한 익명투표 앱이야.

## 기능

- 누구나 의제를 만들 수 있음
- 선택지는 줄바꿈이나 쉼표로 입력
- 사용자가 입력한 익명 투표 코드 기준으로 한 의제당 1회만 투표
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

익명 투표 코드는 원문을 저장하지 않고 해시로만 저장돼. 같은 코드를 입력하면 같은 사람으로 처리되므로 같은 의제에 다시 투표할 수 없어.

로그인 없는 간이 앱 특성상 누군가 일부러 다른 코드를 만들어 쓰는 것까지 완전히 막을 수는 없어. 정말 강하게 막아야 하면 로그인, 초대 토큰, 학교/회사 계정 인증 같은 방식이 필요해.

Streamlit Cloud의 로컬 파일 저장소는 앱 재시작이나 재배포 때 초기화될 수 있어. 장기간 투표 데이터를 보존해야 하면 Supabase, PostgreSQL 같은 외부 DB로 바꾸는 게 좋아.
