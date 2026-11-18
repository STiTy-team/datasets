# northstar-260928

5명이 연기한 고깃집 비즈니스 저녁. 영어와 한국어가 섞인 대화를 여섯 장면으로 녹음했다. 항목 하나는
대본 줄 하나의 구간(`offset`)이고, 장면 하나가 `group` 하나다.

## 정답은 녹음에서 들리는 말이다

대본이 아니라 녹음을 듣고 적은 것이 정답이다. 배우가 대본과 다르게 말한 곳(숫자를 바꿔 말함,
말을 덧붙임)은 말한 대로, 그 구간 안에서 다른 사람이 한 말(점원의 "어서오세요" 등)도 정답에 들어간다.
교정 과정과 기준: [Confluence r1 문서](https://stity.atlassian.net/wiki/spaces/STiTy/pages/34045962/r1)

말이 아닌 소리(웃음 `하하하`, 헛기침 `크흠`·`흠흠`, 한숨 `후`)는 정답에 넣지 않는다(r2). 원문에서 뺀 소리에 해당하는 번역 표기(Hahaha, Ahem, Phew)도 뺐다. 원문에 남은 말을 옮긴 번역(에휴 → Sigh 등)은 그대로다. r2 정답으로 채점할 때는 bench 에 `STITY_R2NORM=all` 을 준다 — 군말·같은 말의 다른 표기·사투리 어미를 양쪽에서 맞춘다. 기준과 근거: [Confluence r2 문서](https://stity.atlassian.net/wiki/spaces/STiTy/pages/46104577)

`reference` 의 필드:

| 필드 | 무엇 |
|---|---|
| `transcript`, `translations` | 그 구간에서 들리는 말 전부. bench 가 채점에 쓰는 것 |
| `transcript_speaker`, `translations_speaker` | 그 줄의 화자가 한 말만 |
| `transcript_script` | 대본 원문 |
| `others` | 다른 사람이 한 말, 화자와 번역 |
