# STiTy 벤치 데이터셋

코퍼스를 내려받아 **STiTy `bench/` 가 읽는 공통 형태**로 변환하는 스크립트 모음이다.
오디오와 생성물은 git 에 넣지 않는다 — 스크립트만 추적하고, 데이터는 각자 만든다.

이 리포를 체크아웃한 **디렉토리 자체가 `STITY_DATA_ROOT`** 다.

```bash
git clone git@github.com:STiTy-team/datasets.git ~/datasets
export STITY_DATA_ROOT=~/datasets            # 쉘 프로필에 넣어 두면 편하다

cd ~/datasets && pip install -r requirements.txt
bash fleurs/install.sh                        # 내려받고 변환까지 한다

cd ~/STiTy && make bench CONFIG=bench/configs/fleurs.yml
```

## 들어 있는 것

| 디렉토리 | 코퍼스 | 항목 하나 | 세션(`group`) | 받는 방법 |
|---|---|---|---|---|
| `fleurs/` | FLoRes 문장 낭독, 102개 언어 n-way 병렬 | 문장 하나 | 항목마다 새로 | 스크립트가 받는다 |
| `acl6060/` | ACL 학회 발표, en → de/ja/zh 등 | gold 문장 하나 | 발표 하나 | 직접 받아 푼다 |

각 디렉토리에 `install.sh`(받기), `convert.py`(변환), `README.md`(그 코퍼스 이야기)가 있다.

## 디렉토리 하나가 어떻게 생겼나

```
<name>/
  install.sh        받아서 convert.py 까지 부른다
  convert.py        원본 배치 → 아래 셋
  README.md
  data/ 또는 원본 디렉토리      ← git 에 없다. install.sh 가 만든다
  dataset.yml       ← git 에 없다. 생성물
  manifest.jsonl    ← git 에 없다. 생성물
  audio -> ...      ← git 에 없다. 원본으로의 심볼릭 링크
```

원본을 복사하지 않고 **심볼릭 링크**만 건다. 코퍼스가 수 GB 이고 bench 는 읽기만 한다.

## bench 가 읽는 계약

`dataset.yml` 이 입력 형식과 가진 참조를 선언하고, `manifest.jsonl` 이 항목을 한 줄씩 담는다.

```yaml
name: fleurs
split: test-en_us
languages: [en]                 # 여러 언어가 섞인 대화면 [en, ko, fr]
audio:
  format: wav                   # flac | wav | pcm_s16le
  sample_rate: 16000
provides:
  transcript: true
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

### 지켜야 하는 규칙 넷

**`audio` 는 데이터셋 디렉토리 기준 상대경로다.** 절대경로를 담으면 데이터가 움직이는
순간 깨지고, 다른 머신과 공유할 수도 없다.

**`duration` 은 필수다.** LAAL 의 소스 길이 `T` 라서, 오디오를 디코딩해 구하면 지연
지표가 로더 구현에 의존하게 된다. 선언값과 실제 길이가 50ms 이상 어긋나면 검증이 잡는다.

**`audio.format` 은 반드시 선언한다.** 헤더 없는 PCM 은 추측할 수 없고, 추측을 시도하면
flac 을 잡음으로 "성공적으로" 읽어버린다.

**`group` 이 세션 경계다.** 같은 `group` 의 항목은 STiTy 핸들러 **하나**를 이어서 쓰고,
값이 바뀌면 새 핸들러를 만든다. 취향이 아니라 정확성 문제다 — `init_streaming_state()` 가
여섯 개 속성(`vad_speech_spans`, `_last_final_end_sec`, `_last_final_text`,
`_deferred_fragment`, `_gpt_flush_tasks`, `vad_last_speech_start_sample`)을 되돌리지
않아서, 무관한 클립을 한 핸들러로 이어 돌리면 앞 항목의 좌표와 꼬리 문장이 뒤 항목에
새어 든다. `group` 을 안 적으면 `id` 가 되고, 즉 **기본은 항목마다 새 세션**이다.

그룹 **안**에서는 manifest 에 쓴 순서가 그대로 유지된다. ACL 60/60 이 이걸 쓴다 —
gold 문장 경계가 겹쳐서 발화 순서가 seg id 순서와 어긋난다.

## 검증

변환기가 끝에 스스로 확인하지만, 최종 판정은 bench 쪽이 한다.

```bash
cd ~/STiTy
python -m bench.data.manifest --validate $STITY_DATA_ROOT/fleurs
make validate DATA=fleurs
```

경로 존재, 선언 길이와 실제 길이 일치, 빈 전사 없음, `provides.translations` 에 적은
언어의 참조가 실제로 있는지를 본다.

`manifest.jsonl` 의 sha256 이 실행 결과의 fingerprint 에 들어간다. 이름만 같고 내용이
다른 데이터셋이 비교 가능한 실행으로 위장하지 못한다.

## 새 코퍼스 붙이기

`<name>/` 에 `install.sh` 와 `convert.py` 를 만든다. `convert.py` 는 자기 디렉토리에
`dataset.yml` / `manifest.jsonl` / `audio` 링크를 쓰고 끝에 자체 검사를 돌린다.
`_contract.py` 의 헬퍼를 쓰면 계약을 외울 필요가 없다.

**STiTy 리포를 import 하지 않는다.** 이 리포는 혼자 돌아야 한다 — 두 리포가 나란히
체크아웃돼 있다는 가정은 곧 깨진다.
