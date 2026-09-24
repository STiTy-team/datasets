# 데이터셋 매니저

리포 루트의 데이터셋을 브라우저에서 열어 **살펴보고**, 새 항목을 **녹음해 넣는** 도구다.
탭이 둘이다.

```bash
make manager                                    # http://127.0.0.1:8765
make manager ROOT=../STiTy-remote/datasets      # 다른 곳의 데이터셋
make manager PORT=9000
```

웹 프레임워크가 없다. `dataset.yml` 을 읽고 쓰느라 `_contract` 를 거쳐 PyYAML 을,
오디오 헤더를 읽느라 soundfile 을 쓰고, 나머지는 전부 표준 라이브러리다.

## 데이터셋 목록

루트의 디렉토리가 그대로 목록이 되고, 한 단계 아래에 `dataset.yml` 이나 `manifest.jsonl`
이 있으면 그것도 따로 뜬다 — 소스 언어마다 나뉜 코퍼스(`fleurs/en_us`, `covost2/de_en`,
`mls/german`)와 `fleurs/mix.py` 가 만든 섞인 대화(`fleurs/ko_kr+en_us.switch0.9-gap0-0.5-cut0.3`)가
그렇다. 이름이 bench 의 `name:` 과 같다. 하위 디렉토리 이름에는 섞인 대화의 이름 때문에 `+` 와
`.` 도 올 수 있다. 빈 디렉토리도 뜬다 — `dataset.yml` 을 요구하면 방금 만들어 녹음하려는
디렉토리가 목록에서 빠지는데, 그때가 가장 보여야 할 때다.

`+ 새 데이터셋` 으로 이름과 언어를 주면 루트에 디렉토리가 생기고 `dataset.yml` 과
README 초안이 함께 놓인다. 언어는 쉼표나 공백으로 여러 개를 적는다 — `ko, en, ja` 처럼.
이름은 영문·숫자·`_`·`-` 만, 64자 이내다.

## 살펴보기

**모양.** manifest 를 통째로 읽어 요약한다.

- 있는 파일 (`dataset.yml`, `manifest.jsonl`, `alignment.jsonl`, `README.md`, `convert.py`).
  `dataset.yml` 은 원문 그대로 보이므로 섞인 대화의 `mix` 설정도 여기 보인다
- 항목 수, 총 길이, 세션(`group`) 수와 연속성, 화자 수, 오디오 파일 수와 없는 파일 수,
  `offset`·`partial` 항목 수
- 길이 분포 (min · p50 · mean · p90 · max 와 구간별 막대)
- `src_lang` 분포, 전사·번역 참조가 채워진 비율 (선언과 다르면 표시), 전사 길이
- 정렬: 정렬된 항목 수, 옛 전사로 정렬된 항목, manifest 에 없는 항목
- **행의 필드**: 행들이 실제로 어떤 키를 어떤 JSON 타입으로 몇 번 갖고 있나.
  `reference.translations.<lang>` 까지 펼친다. 계약 밖 키(`speakers` 등)도 여기 보인다
- manifest 의 sha256 — bench 가 실행 결과에 기록하는 그 값

`dataset.yml` 원문과, 버튼 하나로 `_contract.verify()` 결과도 본다. 오디오 헤더를 전부
읽으므로 큰 데이터셋에서는 몇 초 걸린다.

**항목.** 한 번에 100개씩 manifest 순서대로 보인다. id · 전사 · 번역 · speaker · group 으로
검색한다. 항목을 누르면 펼쳐진다.

- 오디오 재생. `offset` 이 있는 항목은 **그 구간만** 잘라 보내므로 bench 가 읽는 것과 같다
- 오디오 파일 헤더 (형식 · 레이트 · 채널 · 실제 길이) 와 계약 위반이면 그 이유
- 전사와 번역 전문
- 정렬된 단어들. 누르면 그 단어부터 재생되고, 재생 중인 단어가 칠해진다
- manifest 의 원래 행과 줄 번호

**골라낸다.** `오디오 삭제` 는 wav 만 지우고 행은 남긴다 (`verify()` 가 그 항목을
`audio missing` 으로 잡는다 — 실제로 그 상태이므로 맞는 보고다). `항목 삭제` 는 행과
wav 를 같이 지운다. 둘 다 한 번 더 눌러야 실행된다. `offset` 으로 한 파일을 나눠 쓰는
항목이면 파일은 지우지 않는다 — 오디오 삭제는 거부되고, 항목 삭제는 행만 지운다.

`audio` 는 심볼릭 링크라 **오디오 삭제는 링크 너머의 파일을 지운다** — 원본 코퍼스일 수도 있고
(`acl6060`), 계약 형식으로 다시 쓴 사본(`data/wav16k/`)이나 합성한 대화(`data/mixed/`)일 수도 있다.
사본을 지우면 `convert.py`·`mix.py` 를 다시 돌려야 돌아온다.

## 녹음

take 하나가 항목 하나다. wav 는 `<dataset>/data/sessions/` 에 떨어지고 계약 형식의 행이
`manifest.jsonl` 끝에 붙는다. 오른쪽에 마지막 20개 항목이 최근 것부터 보인다.
`dataset.yml` 이 없는 데이터셋이면 첫 take 가 만들어 준다 — 매니저 밖에서 만든
디렉토리도 그래서 그냥 쓸 수 있다.

`src_lang` 은 그 데이터셋이 선언한 언어 중에서 고르되 (입력칸이 목록을 띄운다), 선언에
없는 언어를 적으면 `dataset.yml` 의 `languages` 에 그 언어가 추가된다. 한 데이터셋이
여러 소스 언어를 담을 수 있고, 스펙은 실제로 들어 있는 것을 따라간다.

## manifest.jsonl 을 직접 고쳐 쓴다

읽는 것도 쓰는 것도 `manifest.jsonl` 이다. 별도 오버레이가 없으므로 `convert.py` 를 다시
돌리면 여기서 한 편집은 사라진다. 변환되는 데이터셋에서는 그게 맞는 동작이고 (원본은
상류 코퍼스다), 손으로 녹음하는 데이터셋에는 애초에 `convert.py` 가 없다.

전사는 여기서 쓰지 않는다. 오디오를 넣고 파이프라인이 무엇을 받는지 보는 게 목적이라,
녹음된 항목의 `reference.transcript` 는 빈 문자열로 남는다. 그래서 이 도구가 쓰는
`dataset.yml` 은 `provides.transcript: false` 를 선언하고, 계약의 `verify()` 는 빈 전사를
문제 삼지 않는다.

## 왜 서버가 있나

페이지가 파일을 데이터셋에 직접 쓰면 될 것 같지만, 마이크를 열려면 보안 컨텍스트가
필요하다. 브라우저는 `file://` 페이지에 `getUserMedia` 를 내주지 않으므로 어차피
`http://localhost` 로 띄워 줄 프로세스가 하나 있어야 한다. 그 프로세스가 파일까지 쓰는
편이 File System Access API 를 쓰는 것보다 기계 장치가 적고, Chrome 계열 밖에서도 돈다.

그래서 서버는 있지만 프레임워크는 없다. FastAPI · uvicorn · python-multipart 가 하던
일 — 정적 파일, JSON 몇 개, 바이트 한 덩이 받기 — 은 `http.server` 로 충분하다.
의존성 셋이 빠지고 코드는 100줄쯤 늘었다.
페이지가 유일한 클라이언트라 s16le 한 덩이를 multipart 봉투에 넣고 그걸 풀 파서를
들여올 이유도 없다: 본문은 PCM 그대로고, take 의 나머지 정보는 쿼리 문자열에 있다.

`<audio>` 가 탐색할 수 있도록 Range 요청만 직접 처리한다.

## 왜 이렇게 녹음하나

**MediaRecorder 를 쓰지 않는다.** 브라우저가 주는 건 webm/opus 다. 계약이 요구하는
16 kHz s16le wav 로 가려면 ffmpeg 의존성이 붙고 손실 세대가 하나 낀다. 페이지가 오디오
그래프에서 float 샘플을 직접 받으므로 변환 단계가 없다.

**AudioContext 를 16 kHz 로 연다.** 브라우저가 거부하면 재샘플링하지 않고 그 자리에서
에러를 띄운다. 조용히 어긋난 레이트로 녹음하느니 못 하는 게 낫다.

**브라우저 DSP 는 항상 꺼져 있다.** 잡음 억제기는 겹친 두 번째 목소리를 잡음으로 보고
지우도록 학습돼 있다. `overlap` 이 담으려는 것이 정확히 그 목소리다. 토글은 없다.

**take 는 정지할 때까지 메모리에 있다.** 탭을 닫으면 그 take 는 사라진다. 16 kHz mono
s16le 는 분당 약 1.9 MB 라 한 시간짜리도 메모리에는 무리가 없다.

<kbd>Space</kbd> 또는 버튼으로 시작하고 다시 눌러 멈춘다. 0.25초 미만은 오발로 보고 버린다.

## 디스크에 남는 것

```
overlap/
  dataset.yml               ← 첫 take 가 만든다 (git 에 없다)
  manifest.jsonl            ← 여기서 읽고 쓴다 (git 에 없다)
  data/sessions/            ← git 에 없다 (.gitignore 의 data/)
    ov_20260912_204124.wav    16 kHz · mono · s16le
```

```json
{"id": "ov_20260912_204124",
 "audio": "data/sessions/ov_20260912_204124.wav",
 "duration": 12.412,
 "group": "ov_20260912_204124",
 "speaker": "",
 "src_lang": "ko",
 "reference": {"transcript": "", "translations": {}},
 "speakers": 2}
```

`speakers` 는 계약 필드가 아니다. 겹친 take 에서는 그게 핵심이고 녹음하는 순간에만 알 수
있어서 같이 싣는다. `verify()` 는 모르는 키를 무시한다.

## 옵션

```
--root <path>          데이터셋이 있는 루트 (기본: 이 리포)
--host / --port        기본 127.0.0.1:8765
--open                 브라우저 탭을 띄운다
```

`--host 0.0.0.0` 으로 팀원 노트북에서 붙는 건 안 된다. 브라우저는 보안 컨텍스트
(localhost 또는 https) 에서만 마이크를 내준다. 각자 자기 노트북에서 띄우는 쪽이 맞다.
