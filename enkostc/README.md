# EnKoST-C

영어 TED 강연에 한국어 번역을 붙인 en→ko 음성번역 코퍼스(ETRI,
[ETRI Journal 2023](https://doi.org/10.4218/etrij.2021-0336), CC BY-NC-ND 4.0).
영어를 소스로 **한국어 번역 참조**가 있는 거의 유일한 공개 장문 코퍼스다.

```bash
./enkostc/install.sh                      # tst-COMMON: 강연 27개, 2,532 구간, 4.0 시간
SPLIT=tst-HE ./enkostc/install.sh         # tst-HE: 강연 11개, 544 구간, 1.1 시간
```

| 분할 | 강연 | 시간 | 구간 |
|---|---|---|---|
| train | 3,138 | 558.8 | 340K |
| dev | 11 | 2.5 | 1,585 |
| tst-COMMON | 27 | 4.0 | 2,532 |
| tst-HE | 11 | 1.1 | 544 |

dev·test 는 사람이 정렬했고 train 은 자동 정렬이다. 강연은 MuST-C 의 dev·tst-COMMON·tst-HE 와 같다.

## 직접 받아서 넣어야 한다

배포처는 ETRI **AI 나눔** 한 곳뿐이다: <https://nanum.etri.re.kr/share/seungyun/EnKoSTCv10>.
로그인이 필요한 것으로 보이고, 서버가 자주 응답하지 않는다(2026-09 확인 시 모든 포트가 연결 거부).
HF·GitHub·Zenodo 사본은 없다. 안 되면 교신저자(Seung Yun, syun@etri.re.kr)에게 문의한다.

1. 위 페이지에서 릴리스(적어도 쓰려는 분할)를 받는다.
2. 받은 archive(`.tar.gz`/`.zip`)를 `enkostc/data/` 에 넣는다.
3. `./enkostc/install.sh` — 풀고 변환한다.

## MuST-C 와 같은 모양이다 (확인 필요)

논문은 "MuST-C 와 같은 구조"라고만 적었다. `convert.py` 는 MuST-C 규칙을 따른다.

```
<어딘가>/<split>/wav/ted_<id>.wav      강연 하나, 16 kHz 16-bit
<어딘가>/<split>/txt/<split>.yaml      - {duration: 3.5, offset: 16.09, speaker_id: spk.767, wav: ted_767.wav}
<어딘가>/<split>/txt/<split>.en        yaml 과 같은 줄에 영어 문장
<어딘가>/<split>/txt/<split>.ko        yaml 과 같은 줄에 한국어 번역
```

`data/` 아래 어디에 풀리든 `<split>.yaml` 을 찾아 쓴다. **실제 릴리스를 아직 열어 보지 못했다.** 파일
이름(`.ko` 접미사 등)이 다르면 `convert.py` 가 멈추고 무엇이 없는지 알려 준다 — 그때 고친다. 세 파일의
줄 수가 다르면 변환을 거부한다.

## 항목과 세션

`tedlium/` 과 같다. yaml 구간 하나가 항목 하나이고 `offset`·`duration` 으로 강연 wav 안을 가리킨다
— **파일을 자르지 않는다.** `group` 은 강연이고 강연 안 순서는 시작 시각이다. wav 가 이미 계약
형식이면 링크만 걸고, 아니면 `data/wav16k/<split>/` 에 다시 쓴다.

## 라이선스

CC BY-NC-ND 4.0 — 비영리, 변경물 배포 금지.

## 만들어지는 것

```
enkostc/
  data/*.tar.gz|*.zip          직접 넣은 것 (git 에 없다)
  data/**/<split>/{wav,txt}/   푼 것 (git 에 없다)
  dataset.yml, manifest.jsonl, alignment.jsonl   생성물
  audio -> data/**/<split>/wav  심볼릭 링크
```
