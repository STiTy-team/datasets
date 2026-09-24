# STiTy 벤치 데이터셋

코퍼스를 내려받아 **STiTy `bench/` 가 읽는 공통 형태**로 변환하는 스크립트 모음이다.
오디오와 생성물은 git 에 넣지 않는다 — 스크립트만 추적하고, 데이터는 각자 만든다.

이 리포를 체크아웃한 **디렉토리 자체가 `STITY_DATA_ROOT`** 다.

```bash
git clone git@github.com:STiTy-team/datasets.git ~/datasets
export STITY_DATA_ROOT=~/datasets            # 쉘 프로필에 넣어 두면 편하다

cd ~/datasets
bash fleurs/install.sh                        # 내려받고 변환·정렬까지 한다

cd ~/STiTy && make bench CONFIG=baseline DATASET=fleurs-en-ko
```

## 들어 있는 것

| 디렉토리 | 코퍼스 | 항목 하나 | 세션(`group`) | 받는 방법 |
|---|---|---|---|---|
| `fleurs/` | FLoRes 문장 낭독, 102개 언어 n-way 병렬 | 문장 하나 | 항목마다 새로 | 스크립트가 받는다 |
| `acl6060/` | ACL 학회 발표, en → de/ja/zh 등 | gold 문장 하나 (`offset`) | 발표 하나 | 직접 받아 푼다 |
| `mcif/` | ACL 2023 발표, en → de/it/zh. IWSLT 2025 test | 발표 하나 | 발표 하나 | 스크립트가 받는다 |
| `tedlium/` | TED 강연, en ASR | STM 구간 하나 (`offset`) | 강연 하나 | 스크립트가 받는다 (비공식 사본) |
| `covost2/` | Common Voice 낭독, de ↔ en | 클립 하나 | 항목마다 새로 | 스크립트가 받는다 (비공식 미러) |
| `mls/` | 오디오북 낭독, de 등 8개 언어 ASR | 클립 하나 | 항목마다 새로 | 스크립트가 받는다 |
| `kosp2e/` | 한국어 낭독·구어, ko → en, 전사 없음 | 발화 하나 | 항목마다 새로 | 스크립트가 받는다 (약 1시간) |
| `bstc/` | 중국어 강연, zh → en, dev 만 | 발표 하나 | 발표 하나 | 스크립트가 받는다 |

각 디렉토리에 `install.sh`(받기), `convert.py`(변환), `README.md`(그 코퍼스 이야기)가 있다.

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

## bench 가 읽는 계약

`dataset.yml` 이 입력 형식과 가진 참조를 선언하고, `manifest.jsonl` 이 항목을 한 줄씩 담는다.

```yaml
name: fleurs
split: test-en_us
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

**`group` 이 세션 경계다.** 같은 `group` 의 항목은 STiTy 핸들러 **하나**를 이어서 쓰고,
값이 바뀌면 새 핸들러를 만든다. 취향이 아니라 정확성 문제다 — `init_streaming_state()` 가
여섯 개 속성(`vad_speech_spans`, `_last_final_end_sec`, `_last_final_text`,
`_deferred_fragment`, `_gpt_flush_tasks`, `vad_last_speech_start_sample`)을 되돌리지
않아서, 무관한 클립을 한 핸들러로 이어 돌리면 앞 항목의 좌표와 꼬리 문장이 뒤 항목에
새어 든다. `group` 을 안 적으면 `id` 가 되고, 즉 **기본은 항목마다 새 세션**이다.

그룹 **안**에서는 manifest 에 쓴 순서가 그대로 유지된다. ACL 60/60 이 이걸 쓴다 —
gold 문장 경계가 겹쳐서 발화 순서가 seg id 순서와 어긋난다.

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
