# STiTy 벤치 데이터셋

코퍼스를 내려받아 **STiTy `bench/` 가 읽는 공통 형태**로 변환하는 스크립트 모음이다.
오디오와 생성물은 git 에 넣지 않는다 — 스크립트만 추적하고, 데이터는 각자 만든다.

이 리포를 체크아웃한 **디렉토리 자체가 `STITY_DATA_ROOT`** 다.

```bash
git clone git@github.com:STiTy-team/datasets.git ~/datasets
export STITY_DATA_ROOT=~/datasets            # 쉘 프로필에 넣어 두면 편하다

cd ~/datasets
SRC="en_us ko_kr" TGT=ko_kr bash fleurs/install.sh   # fleurs/en_us, fleurs/ko_kr: 같은 270문장

cd ~/STiTy && make bench CONFIG=asr.qwen-seg+mt.qwen3.5-4b DATASET=fleurs-en-ko
```

## 들어 있는 것

| 디렉토리 | 코퍼스 | 항목 하나 | 세션(`group`) | 받는 방법 |
|---|---|---|---|---|
| `fleurs/` | FLoRes 문장 낭독, 102개 언어 n-way 병렬 | 문장 하나 | 항목마다 새로 | 스크립트가 받는다 |
| `acl6060/` | ACL 학회 발표, en → de/ja/zh 등 | gold 문장 하나 (`offset`) | 발표 하나 (HF 경로는 항목 하나) | 스크립트가 받는다 (HF 미러). 발표 단위가 필요하면 직접 받아 푼다 |
| `mcif/` | ACL 2023 발표, en → de/it/zh. IWSLT 2025 test | 발표 하나 | 발표 하나 | 스크립트가 받는다 |
| `tedlium/` | TED 강연, en ASR | STM 구간 하나 (`offset`) | 강연 하나 | 스크립트가 받는다 (비공식 사본) |
| `covost2/` | Common Voice 낭독, de ↔ en | 클립 하나 | 항목마다 새로 | 스크립트가 받는다 (비공식 미러) |
| `mls/` | 오디오북 낭독, de 등 8개 언어 ASR | 클립 하나 | 항목마다 새로 | 스크립트가 받는다 |
| `kosp2e/` | 한국어 낭독·구어, ko → en, 전사 없음 | 발화 하나 | 항목마다 새로 | 스크립트가 받는다 (약 1시간) |
| `bstc/` | 중국어 강연, zh → en, dev 만 | 발표 하나 | 발표 하나 | 스크립트가 받는다 |
| `ami/` | 회의, en ASR, 화자 겹침 | 주석 구간 하나 (`offset`) | 회의 하나 | 스크립트가 받는다 |
| `notsofar/` | 실제 사무실 회의, en ASR, 겹침·잡음 태그 | 발화 하나 (`offset`) | 회의 하나 | 스크립트가 받는다 (HF, 장치 하나만) |
| `earnings22/` | 실적발표 통화, 억양 있는 en ASR, 장문 | 구간 하나 (`offset`) | 통화 하나 | 스크립트가 받는다 (구간 표는 HF 미러) |
| `enkostc/` | TED 강연, en → ko | yaml 구간 하나 (`offset`) | 강연 하나 | **직접 받아 넣는다** (ETRI AI 나눔) |
| `zeroth/` | 한국어 뉴스 낭독, ko ASR | 발화 하나 | 항목마다 새로 | 스크립트가 받는다 (HF 미러) |
| `ksponspeech/` | 한국어 자유 대화, ko ASR | 발화 하나 | 항목마다 새로 | 스크립트가 받는다 (**AI Hub 승인·API 키 필요**) |
| `musan/` | 잡음·음악·말소리. 위 데이터셋에 섞는다 | 원본과 같다 | 원본과 같다 | 스크립트가 받는다 (11 GB 를 흘려 받는다) |

각 디렉토리에 `install.sh`(받기), `convert.py`(변환), `README.md`(그 코퍼스 이야기)가 있다.

## 들여다보기와 녹음

`manager/` 는 데이터셋을 브라우저에서 여는 도구다. 스펙과 모양(길이 분포, 언어, 참조 채움,
행의 필드, 정렬), 항목마다 오디오와 단어 시각을 보고, 새 항목을 녹음해 넣는다.

```bash
make manager
```

자세한 건 [`manager/README.md`](manager/README.md).

## 의존성

[uv](https://docs.astral.sh/uv/) 가 맡는다. 따로 설치하는 단계도, 활성화할 venv 도 없다 —
`install.sh` 와 `uv run` 이 실행 직전에 환경을 맞춘다.

```bash
uv run python fleurs/convert.py --help   # 필요한 것을 깔고 바로 돌린다
uv sync                                  # 환경만 미리 맞춰 두고 싶을 때
```

| 파일 | 무엇 |
|---|---|
| `pyproject.toml` | 무엇이 필요한지. 라이브러리가 아니므로 `package = false` 다 |
| `uv.lock` | 정확히 어떤 버전인지. **커밋한다** — 플랫폼을 가리지 않는다 |
| `.python-version` | 3.14. 없으면 uv 가 받아서 쓴다 |

변환에 필요한 건 `PyYAML`, `soundfile`, `numpy`, `soxr` 이다. 뒤의 셋은 원본을 계약의
오디오 형식으로 다시 쓰는 데 쓰인다 — mp3·opus·sph 디코딩까지 `soundfile` 에 딸린
libsndfile 이 하므로 ffmpeg 는 필요 없다. 오디오를 parquet 에 담아 배포하는 코퍼스
(`mls/`, `covost2/`)를 푸는 데 `pyarrow`, `kosp2e/` 의 분할 목록(xlsx)을 읽는 데
`openpyxl` 이 쓰인다. 변환 끝의 정렬(아래 "정렬")에 `qwen-asr` 가 쓰이고, 그게 torch 를
끌고 온다.

내려받기에만 쓰는 것은 `download` 그룹에 따로 두었다 — Hugging Face 에서 받는
`install.sh` 들이 부르는 `hf` CLI, 그리고 `kosp2e/install.sh` 가 17 GB zip 에서 필요한
wav 만 꺼내는 `remotezip` 이다. 변환만 다시 돌릴 때는 받을 이유가 없다.

```bash
uv run --group download hf download ...   # install.sh 가 이렇게 부른다
```

`uv` 없이 돌려야 하면 `PYTHON` 으로 인터프리터를 직접 지정한다.

```bash
PYTHON=.venv/bin/python bash fleurs/install.sh
```

## 디렉토리 하나가 어떻게 생겼나

```
<name>/
  install.sh        받아서 convert.py 까지 부른다
  convert.py        원본 배치 → 아래 셋
  README.md
  data/ 또는 원본 디렉토리      ← git 에 없다. install.sh 가 만든다
  dataset.yml       ← git 에 없다. 생성물
  manifest.jsonl    ← git 에 없다. 생성물
  alignment.jsonl   ← git 에 없다. 생성물 (정렬할 항목이 없으면 없다)
  audio -> ...      ← git 에 없다. 원본으로의 심볼릭 링크
```

원본이 이미 계약 형식(16 kHz mono PCM16 wav)이면 복사하지 않고 **심볼릭 링크**만 건다.
코퍼스가 수 GB 이고 bench 는 읽기만 한다. 아니면(mp3, opus, sph, 헤더 없는 pcm, parquet
안의 바이트) `contract.transcode()` 로 `data/` 아래에 한 번 다시 쓰고 `audio` 를 그쪽으로 건다.

**여러 언어로 된 코퍼스는 소스 언어마다 데이터셋 하나다.** `fleurs/`·`covost2/`·`mls/` 는 소스
언어(또는 방향)마다 하위 디렉토리(`fleurs/en_us/`, `covost2/de_en/`, `mls/german/`)에 위 파일들을
따로 만든다. 원본(`data/`)은 함께 쓴다. bench 의 데이터셋 설정은 이 하위 디렉토리를 이름으로
고른다(`name: fleurs/en_us`). 여러 언어가 한 입력에 섞인 데이터셋이 필요하면 그 옆에 따로 만든다.

## bench 가 읽는 계약

`dataset.yml` 이 입력 형식과 가진 참조를 선언하고, `manifest.jsonl` 이 항목을 한 줄씩 담는다.

```yaml
name: fleurs/en_us
split: test
languages: [en]                 # 여러 언어가 섞인 대화면 [en, ko, fr]
audio:
  format: wav                   # 항상 wav. write_spec 이 채운다
  sample_rate: 16000            # 항상 16000
provides:
  transcript: true              # 소스 전사가 없는 코퍼스면 false
  translations: [ko, de]        # 번역 참조가 있는 언어
primary_metric: wer             # wer | cer
group_rule: "id"                # 사람이 읽는 설명. 실제 기준은 manifest 의 group 열
bench_defaults:
  trailing_silence_ms: 4000
```

```json
{"id": "en_1", "audio": "audio/1_a.wav", "duration": 1.2,
 "group": "en_1", "speaker": "spk1", "src_lang": "en",
 "reference": {"transcript": "Hello there friend",
               "translations": {"ko": "안녕 친구"}}}
```

### 지켜야 하는 규칙

**`audio` 는 데이터셋 디렉토리 기준 상대경로다.** 절대경로를 담으면 데이터가 움직이는
순간 깨지고, 다른 머신과 공유할 수도 없다.

**`duration` 은 필수다.** LAAL 의 소스 길이 `T` 라서, 오디오를 디코딩해 구하면 지연
지표가 로더 구현에 의존하게 된다. 선언값과 실제 길이가 50ms 이상 어긋나면 검증이 잡는다.

**오디오 형식은 하나다: 16 kHz mono PCM16 wav.** bench 로더는 선언을 보지 않고
soundfile 로 파일 헤더를 읽는다. 형식을 코퍼스마다 고를 수 있던 때는 헤더 없는
`pcm_s16le` 가 검증은 통과하고 bench 에서 터졌다. 이제 변환기가 무엇이든
`contract.transcode()` 로 이 형식으로 만들고, `verify()` 는 파일마다 헤더를 확인한다.

**전사는 없어도 된다.** ST 참조만 있는 코퍼스(`kosp2e/`)는
`write_spec(..., transcript=False)` 로 `provides.transcript: false` 를 선언한다. 그러면
`verify()` 가 빈 전사를 문제 삼지 않는다. bench 는 이 값을 실행 결과의
데이터셋 정보에 그대로 기록한다.

**긴 파일 하나에서 구간을 잘라 쓰려면 `offset` 을 적는다.** 강연 하나가 wav 하나이고
문장 경계가 타임스탬프로만 있는 코퍼스(`tedlium/` 의 `.stm`)가 그렇다.
bench 는 `[offset, offset + duration)` 만 읽는다. 파일을 자르지 않아도 되고, 같은 강연의
문장들은 같은 `group` 으로 묶는다. `verify()` 는 구간이 파일 안에 들어가는지 본다.

**중간에 끊긴 발화는 `partial: true` 로 적는다** (`contract.row(..., partial=True)`). 전사는 실제로
말해진 단어까지이고, 번역 참조는 문장 전체의 것을 그대로 둔다 — 반쪽 문장의 번역 참조는 없다.
bench 는 이 항목을 번역 지표에서 빼고 WER·언어 판정에만 쓴다. `mix.py --cut` 이 만든다.

**`group` 이 세션 경계다.** 같은 `group` 의 항목은 STiTy 핸들러 **하나**를 이어서 쓰고,
값이 바뀌면 새 핸들러를 만든다. 취향이 아니라 정확성 문제다 — `init_streaming_state()` 가
여섯 개 속성(`vad_speech_spans`, `_last_final_end_sec`, `_last_final_text`,
`_deferred_fragment`, `_gpt_flush_tasks`, `vad_last_speech_start_sample`)을 되돌리지
않아서, 무관한 클립을 한 핸들러로 이어 돌리면 앞 항목의 좌표와 꼬리 문장이 뒤 항목에
새어 든다. `group` 을 안 적으면 `id` 가 되고, 즉 **기본은 항목마다 새 세션**이다.

그룹 **안**에서는 manifest 에 쓴 순서가 그대로 유지된다. ACL 60/60 이 이걸 쓴다 —
gold 문장 경계가 겹쳐서 발화 순서가 seg id 순서와 어긋난다.

## 언어가 섞인 대화 (`mix.py`)

여러 언어로 된 코퍼스는 언어마다 하위 데이터셋이다(`fleurs/ko_kr/`, `fleurs/en_us/`). `mix.py` 는 그중
둘 이상을 이어 붙여 **대화를 합성하고**, 같은 코퍼스 아래 새 하위 디렉토리로 쓴다.

```bash
SRC="ko_kr en_us" ./fleurs/install.sh                            # 소스를 먼저 만든다 (정렬까지)
uv run python mix.py fleurs --src ko_kr en_us                    # -> fleurs/ko_kr+en_us/
uv run python mix.py fleurs --src ko_kr en_us --switch 0.9 --gap 0 0.5 --cut 0.3
                                                                 # -> fleurs/ko_kr+en_us.switch0.9-gap0-0.5-cut0.3/
uv run python mix.py fleurs --src ko_kr en_us --level -26        # -> fleurs/ko_kr+en_us.level-26/
uv run python mix.py mls --src german french                     # 병렬이 아닌 코퍼스도 된다
```

대화 하나가 wav 하나이고, **차례 하나는 소스 데이터셋의 항목 하나**다. 새 데이터셋에서도 차례 하나가 항목 하나이고,
오디오는 대화 wav 안의 구간(`offset`·`duration`), `group` 은 그 대화다. 그래서 bench 는 차례를 하나씩
흘릴 수도 있고, `longform: true` 로 대화를 통째로 흘려 **말하는 도중 언어가 바뀌는 상황**을 잴 수도 있다.

**병렬 코퍼스면 차례는 모두 다른 문장이다.** 항목 id 에서 `<언어>_` 를 뗀 것(FLEURS 의 `ko_1660` →
`1660`)이 소스끼리 겹치면 병렬로 보고, 문장 하나를 데이터셋 전체에서 한 번만 쓴다. 같은 문장을 언어만
바꿔 연달아 말하면 다음 차례의 참조 번역이 방금 들린 말 그 자체라서, 앞 차례를 문맥으로 받는 번역기가
답을 베낄 수 있다. 이때 차례마다 대화의 모든 언어 참조가 붙는다 — 자기 언어의 것은 같은 문장의 원문이고
다른 소스의 번역 참조에서 가져온다. 계약이 선언한 참조를 모든 항목에 요구하기 때문이고, bench 는 원문
언어가 목표 언어와 같은 차례를 번역 지표에서 빼므로 이 참조로 채점되는 일은 없다. 겹치는 문장이 없으면
소스마다 따로 뽑고, 참조는 `--tgt` 로 고른 언어만 붙는다.

| 손잡이 | 뜻 | 기본 |
|---|---|---|
| `--switch P` | 다음 차례가 다른 언어일 확률. 1 이면 매번 바뀌고(ko, en, ko, …), 낮을수록 한 언어가 이어진다 | 1 |
| `--gap MIN MAX` | 차례 사이 무음(초). 0 이면 쉼 없이 이어져 VAD 가 끊을 틈이 없다 | 0.5 1.5 |
| `--cut P` | 차례가 **말하는 도중 끊길** 확률. 단어 경계에서 잘리고 다음 사람이 이어받는다 — 나머지는 끝내 말해지지 않는다 | 0 |
| `--level DB` | 차례마다 음성 크기를 이 값(dBFS)으로 맞춘다 | 끔 |

`--turns`(대화당 차례 수, 기본 6), `--seed`(기본 0), `--tgt`(참조 언어 추가, 없는 문장은 안 쓴다),
`--limit`(대화 수)도 있다. 무작위는 모두 시드로 고정되어 다시 만들어도 같다. **디렉토리 이름은 기본값과
다른 손잡이로 지어지고**, `dataset.yml` 의 `mix` 에 전부(끊긴 차례 수 `cut_turns` 까지) 남는다.

**끊긴 차례**의 전사는 실제로 말해진 단어까지다. 번역 참조는 문장 전체의 것 그대로이고 — 반쪽 문장의
번역 참조는 없다 — 항목에 `partial: true` 가 붙는다. 끊을 자리는 단어 정렬(`alignment.jsonl`)로 찾으므로
소스 데이터셋이 정렬되어 있어야 한다. 한국어처럼 정렬 조각이 단어보다 잘게 나오는 언어는 글자 수로 맞춰
단어 경계를 찾는다.

### 음성 크기 맞추기 (`--level`)

소스마다 녹음 크기가 다르다. FLEURS test 에서 잰 활성 음성 크기는 ko 평균 −41 dBFS, en −50 dBFS 로
**9 dB 차이**가 나고, 같은 언어 안에서도 표준편차가 10~16 dB 다. 그대로 이으면 언어가 바뀌는 자리마다
소리 크기가 뛰어서, VAD 와 언어 판정이 말이 아니라 크기로 경계를 알아챌 수 있다.

`--level -26` 은 차례마다 **활성 음성 크기**를 −26 dBFS 로 맞춘다. 활성 음성 크기는 20 ms 프레임 중 가장
센 것에서 30 dB 안쪽인 프레임의 평균 세기다(`_contract.active_power`, `musan/` 의 SNR 과 같은 정의) —
클립 앞뒤 무음이 크기를 끌어내리지 않는다. 맞춘 뒤 −26.0 ± 0.1 dBFS 였다. 크기는 끊기 전 클립 전체로
재므로 끊긴 차례도 같은 배율을 받는다. 올리다가 봉우리가 0.99 를 넘으면 거기서 멈추고 조금 작게 둔다 —
그런 차례 수가 `mix.level_held_back_turns` 에 남는다. 기본은 끄는 것이라, 손잡이를 안 주면 예전 결과와
같다.

## 검증

**형식을 보장하는 쪽은 이 저장소다.** 변환기가 끝에 `_contract.py` 로 스스로 확인하고,
bench 는 그 결과가 맞다고 보고 읽기만 한다. 같은 것을 양쪽에서 검사하면 판정하는 쪽이
둘이 되고, 비용이 변환 한 번이 아니라 실행마다 붙는다.

```bash
uv run python fleurs/convert.py --src en_us --tgt ko_kr   # 끝에 검증까지 돌린다
```

경로 존재, 파일마다 16 kHz mono PCM16 wav 인지, 선언 길이와 실제 길이 일치(`offset`
이 있으면 구간이 파일 안에 드는지), `provides.transcript` 가 true 일 때 빈 전사 없음,
`provides.translations` 에 적은 언어의 참조가 실제로 있는지, id 중복, group 연속성, 그리고 `alignment.jsonl` 이 있으면 그 id 와 전사가 manifest 와 맞는지를 본다.

`manifest.jsonl` 의 sha256 은 실행 결과의 데이터셋 정보에 기록된다. 이름만 같고 내용이
다른 데이터셋이 비교 가능한 실행으로 위장하지 못한다.

## 정렬 — 단어마다 언제 발화됐나

전사는 문장 통째라 단어가 오디오의 어디에 있는지 모른다. `convert.py` 가 manifest 를 쓴 직후
`contract.align()` 으로 강제정렬기(`Qwen/Qwen3-ForcedAligner-0.6B`)에 오디오와 참조 전사를 넣어
그걸 재고 `alignment.jsonl` 에 쓴다. bench 의 토큰 방출 지연(단어가 발화된 뒤 화면에 뜨기까지)이
이 파일을 쓴다.

```json
{"id": "en_1660", "transcript": "romanticism had ...", "aligner": "Qwen/Qwen3-ForcedAligner-0.6B",
 "words": [{"word": "romanticism", "start": 0.8, "end": 1.76}, ...]}
```

- 시각은 그 항목 오디오의 시작(`offset` 이 있으면 거기)부터의 초다.
- 중국어·일본어는 글자 하나가 한 줄이고, 한국어는 정렬기가 어절을 더 잘게 나눈다.
- 이미 같은 전사를 같은 방법(`aligner` 칸)으로 정렬한 항목은 건너뛴다. 다시 변환하면 전사나
  방법이 바뀐 항목만 다시 하고, 바뀐 게 없으면 모델도 안 올린다.
- 정렬기가 아는 언어는 11개다(de, en, es, fr, it, ja, ko, pt, ru, yue, zh). 전사가 없는 항목은
  건너뛴다.

**180초가 넘는 항목은 조각으로 나눠 정렬한다.** 정렬기는 모든 단어의 시각을 한 번에 추측하는데,
오디오 끝으로 갈수록 추측이 밀린다 — 5분짜리 발표에서 마지막 30~120단어가 한 시각에 몰려
나왔다. Qwen 자신의 파이프라인도 정렬기에 180초 넘게 넣지 않는다.

1. 오디오를 가장 조용한 지점에서 180초 이하 조각으로 자른다 (`qwen_asr` 의 `split_audio_into_chunks`).
2. 조각마다 ASR(`Qwen/Qwen3-ASR-0.6B`)로 받아 적는다.
3. 받아 적은 글을 참조 전사와 단어 단위로 맞춰, 참조 전사를 조각마다 나눈다. ASR 글은 나눌
   자리를 찾는 데만 쓴다 — 정렬하는 단어는 언제나 참조 전사의 것이다.
4. 조각마다 정렬하고 조각의 시작 시각을 더한다.

TED 강연을 5·10·20분 창으로 잘라 확인했다. 짧은 문장 단위로 정렬한 시각과 비교해 1초 넘게
어긋난 단어가 0.5% 이하다. 한 번에 넣으면 5분에서 이미 9% 였다.
- 한 번에 넣는 오디오는 합쳐서 5분까지다. GPU 메모리는 항목 수가 아니라 오디오 길이를 따라가서,
  5분짜리 발표 8개를 한 번에 넣으면 6 GB GPU 가 넘친다. 299초짜리 하나가 3.9 GiB 를 쓴다.
- GPU 가 없으면 CPU 로 돈다. 느리지만 된다. GPU 로는 FLEURS(268항목)가 1분 안쪽이다.

## 새 코퍼스 붙이기

`<name>/` 에 `install.sh` 와 `convert.py` 를 만든다. `convert.py` 는 자기 디렉토리에
`dataset.yml` / `manifest.jsonl` / `audio` 링크를 쓰고 끝에 자체 검사를 돌린다.
`_contract.py` 의 헬퍼를 쓰면 계약을 외울 필요가 없다.

**STiTy 리포를 import 하지 않는다.** 이 리포는 혼자 돌아야 한다 — 두 리포가 나란히
체크아웃돼 있다는 가정은 곧 깨진다.
