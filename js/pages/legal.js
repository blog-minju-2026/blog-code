/**
 * 이용약관 (/terms) · 개인정보처리방침 (/privacy)
 * 본문은 HTML 에 그대로 있다. 헤더(검색 · 내 메뉴)만 다른 화면처럼 채운다.
 * 내 정보를 받지 못해도 본문은 그대로 읽을 수 있어야 하므로 runPage 의 오류 화면을 쓰지 않는다.
 */
bindVillageSearch(document.getElementById('village-search'));
renderHeaderNav(document.getElementById('header-nav')).catch((err) => console.error(err));
