# 소셜 로그인 켜기 (카카오 · 구글 · 네이버)

제공사마다 앱을 하나씩 만들고, 받은 키를 GitHub Secrets 에 넣은 뒤 다시 배포하면 로그인 화면에 그 제공사 버튼이 나온다.
키를 넣지 않은 제공사는 버튼도 주소(`/accounts/<제공사>/...`)도 열리지 않는다. 세 곳을 다 할 필요는 없다. 하나만 켜도 된다.

콘솔 화면은 제공사가 자주 바꾼다. 아래 메뉴 이름은 2026년 10월 기준이고, 이름이 다르면 비슷한 메뉴를 찾는다.

## 0. 먼저 정해 둘 값

| 값 | 넣을 것 |
| --- | --- |
| 서비스 주소 | `https://hanchae.java21.net` (`HANCHAE_DOMAIN` 앞에 `https://`) |
| Redirect URI (Callback URL) | `https://hanchae.java21.net/accounts/<제공사>/login/callback/` — `<제공사>` 는 `kakao` · `google` · `naver` |
| 로컬에서 해 볼 때 | `http://localhost:8000/accounts/<제공사>/login/callback/` 도 함께 등록해 둔다 (docker compose 기준) |

- Redirect URI 는 **글자 하나까지** 같아야 한다. `https` / `http`, 끝의 `/`, 도메인 앞 `www` 가 다르면 제공사가 거절한다.
- 한채는 callback 주소를 `USE_HTTPS` 로 정한다 (`ACCOUNT_DEFAULT_HTTP_PROTOCOL`). 사이트가 https 로 열리므로 GitHub Secret `USE_HTTPS` 가 `1` 인지 확인한다. 비어 있으면 `http://…/callback/` 으로 보내 https 로 등록한 주소와 어긋난다.
- 서비스 이름은 「한채」. 개인정보처리방침은 `https://hanchae.java21.net/privacy`, 이용약관은 `https://hanchae.java21.net/terms` 를 쓴다.

## 1. 카카오

만드는 곳: [Kakao Developers](https://developers.kakao.com) → 로그인 → **내 애플리케이션**

1. **앱 만들기**: [애플리케이션 추가하기] → 앱 이름 `한채`, 회사명(개인이면 내 이름), 카테고리를 넣고 저장한다. 앱 아이콘은 카카오 로그인 동의 화면에 보이므로 한채 로고를 넣는다.
2. **카카오 로그인 켜기**: 앱 관리 페이지 → [카카오 로그인] → [사용 설정] 의 상태를 **ON**.
3. **Redirect URI · 키**: [앱] → [플랫폼 키] → **REST API 키** 를 연다.
   - 리다이렉트 URI 에 `https://hanchae.java21.net/accounts/kakao/login/callback/` 을 넣는다 (로컬용 주소도 함께).
   - 이 화면의 **REST API 키** → `KAKAO_CLIENT_ID`
   - 같은 키의 **클라이언트 시크릿** → `KAKAO_SECRET`. 지금 카카오는 REST API 키에 클라이언트 시크릿을 기본으로 켜 두므로 반드시 넣는다 (빠지면 토큰을 받지 못해 `/login?social=error` 가 된다).
4. **동의항목**: [카카오 로그인] → [동의항목]
   - **닉네임**: 「필수 동의」 또는 「선택 동의」로 켜고, 동의 목적에 `한채 닉네임 미리 채우기` 처럼 적는다. 한채는 가입 마무리에서 닉네임 칸을 미리 채우는 데만 쓴다.
   - **카카오계정(이메일)**: 일반 앱에서는 켤 수 없다. **비즈 앱**으로 전환하고 [추가 기능 신청]에서 권한을 받아야 한다 (심사에 며칠 걸릴 수 있다). 켜지 않아도 로그인 · 가입은 된다. 대신 이메일 없이 가입되어, 그 회원은 비밀번호 재설정 메일을 받을 수 없다.
   - 프로필 사진 · 전화번호 등 다른 항목은 켜지 않는다 (한채가 쓰지 않는다).
5. 사이트 도메인(플랫폼 Web) 등록은 REST API 로 로그인하는 한채에는 필요 없다. 콘솔이 요구하면 서비스 주소를 넣는다.

키를 받은 뒤 바로 누구나 로그인할 수 있다 (카카오는 별도 검수 없이 열린다. 단 이메일 같은 권한 항목은 위 심사가 필요하다).

## 2. 구글

만드는 곳: [Google Cloud Console](https://console.cloud.google.com) (결제 등록은 필요 없다)

1. **프로젝트 만들기**: 위쪽 프로젝트 선택 → [새 프로젝트] → 이름 `hanchae`.
2. **Google Auth Platform 시작하기**: 메뉴 → **Google Auth Platform** (예전 이름 「OAuth 동의 화면」) → [시작하기]
   - 앱 정보: 앱 이름 `한채`, 사용자 지원 이메일
   - 대상: **외부(External)** — 내부는 같은 Google Workspace 조직 사람만 쓸 수 있다. 나중에 바꾸기 어려우니 처음에 외부로 고른다.
   - 연락처 정보: 내 이메일 → 정책 동의 → 만들기
3. **데이터 액세스**: [데이터 액세스] → [범위 추가 또는 삭제] → `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile` 세 개만. 셋 다 민감하지 않은 범위라 구글의 별도 심사가 없다. 한채는 `profile` · `email` 을 요청한다.
4. **클라이언트 만들기**: [클라이언트] → [클라이언트 만들기]
   - 애플리케이션 유형: **웹 애플리케이션**, 이름 `한채 웹`
   - 승인된 자바스크립트 원본: 비워 둔다 (한채는 서버에서 처리한다)
   - **승인된 리디렉션 URI**: `https://hanchae.java21.net/accounts/google/login/callback/` (로컬용 주소도 함께. 구글은 `http://localhost` 만 http 를 허용한다)
   - 만들면 **클라이언트 ID** → `GOOGLE_CLIENT_ID`, **클라이언트 보안 비밀번호** → `GOOGLE_SECRET`. 보안 비밀번호는 만든 직후에만 전체가 보일 수 있으니 바로 JSON 을 내려받아 안전한 곳에 둔다 (저장소에 올리지 않는다).
5. **게시**: [대상] 의 게시 상태가 처음에는 **테스트**다.
   - 테스트 중에는 [테스트 사용자] 에 넣은 Google 계정만 로그인할 수 있다 (다른 계정은 「액세스 차단됨」).
   - 모두가 쓰게 하려면 [앱 게시] → 프로덕션. 위 세 범위만 쓰면 심사 없이 게시된다. 브랜딩에 로고를 넣으면 브랜드 인증을 요구할 수 있으니, 처음에는 로고 없이 게시해도 된다.

## 3. 네이버

만드는 곳: [NAVER Developers](https://developers.naver.com) → 로그인 → **Application → 애플리케이션 등록**

> 네이버 개발자 센터 문서는 이 안내를 쓰며 직접 열어 보지 못했다. 메뉴 이름이 다르면 화면의 안내를 따른다.

1. **애플리케이션 이름**: `한채` — 네이버 로그인 동의 화면에 그대로 보인다.
2. **사용 API**: **네이버 로그인** 을 고른다.
3. **제공 정보 선택**: 필수로 **이메일 주소**, 추가로 **별명**. 한채는 이메일(인증된 주소)과 별명(닉네임 미리 채우기)만 쓴다. 이름 · 생일 · 휴대전화 등은 고르지 않는다.
4. **로그인 오픈 API 서비스 환경**: **PC 웹** 을 추가하고 (휴대폰 브라우저도 같은 주소라 PC 웹 하나로 된다)
   - 서비스 URL: `https://hanchae.java21.net`
   - 네이버 로그인 Callback URL: `https://hanchae.java21.net/accounts/naver/login/callback/` (로컬용 주소도 추가)
5. 등록하면 [내 애플리케이션] → 한채 → **개요** 에 **Client ID** → `NAVER_CLIENT_ID`, **Client Secret** → `NAVER_SECRET`.
6. **검수 전에는 멤버만**: 등록 직후는 「개발 중」 상태라 [멤버관리] 에 테스트 ID 로 넣은 네이버 계정만 로그인할 수 있다. 내 네이버 아이디를 먼저 넣고 해 본다.
7. **검수 요청**: 누구나 쓰게 하려면 [검수 요청]. 서비스 설명과 네이버 로그인 버튼이 보이는 화면 캡처를 낸다.
   - 네이버는 **로그인 버튼 디자인 가이드**를 지켰는지 본다. 지금 한채 버튼의 로고는 비슷하게 그린 SVG 이고 글자를 먹색으로 바꿨다 (대비 때문에). 검수 전에 네이버가 주는 공식 버튼 이미지 · 로고로 바꾸고 글자를 흰색으로 되돌리는 것이 안전하다 (`js/common.js` 의 `SOCIAL_PROVIDER_MARKS`, `css/hanchae.css` 의 `.btn-social-naver`).

## 4. 키 넣고 배포하기

1. GitHub 저장소 → **Settings → Secrets and variables → Actions → New repository secret** 에 받은 키를 넣는다.

   | Secret | 값 |
   | --- | --- |
   | `KAKAO_CLIENT_ID` · `KAKAO_SECRET` | 카카오 REST API 키 · 클라이언트 시크릿 |
   | `GOOGLE_CLIENT_ID` · `GOOGLE_SECRET` | 구글 클라이언트 ID · 보안 비밀번호 |
   | `NAVER_CLIENT_ID` · `NAVER_SECRET` | 네이버 Client ID · Client Secret |

2. **Actions → deploy → Run workflow** (main) 로 다시 배포한다. Secret 만 바꾸면 배포가 저절로 돌지 않는다.
3. 확인: `https://hanchae.java21.net/api/auth/social` 이 `{"providers":["kakao", ...], ...}` 처럼 넣은 제공사를 돌려주면 켜진 것이다. 로그인 화면 · 마을 첫 화면에 버튼이 나온다.
4. 처음 가입해 본다: 버튼 → 제공사 동의 → 한채의 「가입 마무리」(닉네임 · 약관) → 가입 마치기 → 로그인된 채 돌아온다. 로그아웃 뒤 같은 버튼을 다시 누르면 가입 마무리 없이 바로 로그인돼야 한다.

로컬에서 먼저 해 보려면 `backend/.env` (또는 docker compose 를 띄울 때 환경 변수)에 같은 키를 넣고, 제공사에 로컬용 Redirect URI 를 등록해 둔다.

## 5. 안 될 때

| 보이는 것 | 원인 · 할 일 |
| --- | --- |
| 로그인 화면에 버튼이 없다 | 서버에 키가 없다. `/api/auth/social` 의 `providers` 를 보고, Secret 이름 · 다시 배포를 확인 |
| 카카오 `KOE006` · 구글 `redirect_uri_mismatch` · 네이버 「redirect uri mismatch」 | 제공사에 등록한 Redirect URI 와 한채가 보낸 주소가 다르다. 오류 화면에 나온 주소(`redirect_uri=`)를 그대로 등록하거나, `USE_HTTPS=1` 인지 확인 |
| 카카오 `KOE101` | `KAKAO_CLIENT_ID` 에 REST API 키가 아닌 다른 키(JavaScript 키 등)를 넣었다 |
| 카카오 `KOE205` | 한채가 요청하지 않은 동의항목 문제. [동의항목]에서 닉네임이 켜져 있는지 확인 |
| 구글 「액세스 차단됨」 · 403 | 앱이 테스트 상태인데 테스트 사용자가 아닌 계정이다. 테스트 사용자에 넣거나 앱을 게시 |
| 네이버 로그인이 나만 된다 | 검수 전 「개발 중」 상태. 멤버관리에 넣거나 검수 요청 |
| `/login?social=error` 로 돌아온다 | 서버 로그(`docker logs`)에서 `소셜 로그인 실패:` 줄을 본다. 시크릿이 틀렸거나 빠진 경우가 많다 |
| 이메일 없이 가입된다 | 카카오 일반 앱이거나 제공사가 이메일을 「인증됨」으로 주지 않았다. 정상 동작이다 (한채는 인증된 이메일만 쓴다) |

## 6. 개인정보처리방침에 적을 것

한채가 소셜 로그인으로 저장하는 것은 **제공사 이름과 제공사 쪽 회원 번호**, 그리고 **제공사가 인증한 이메일(받은 경우)** 뿐이다. 닉네임은 가입할 때 회원이 직접 정한다. 제공사의 프로필 원본 · 접근 토큰은 저장하지 않는다.
