# Earnings-22

기업 실적발표 **통화**를 받아 적은 영어 ASR 코퍼스(Rev, CC BY-SA 4.0). 통화 125개, 119 시간,
통화당 15분~2시간. 발표자 대부분이 영어 모국어 화자가 아니다 — **억양**이 요점이다. 번역 참조는 없다.

```bash
./earnings22/install.sh                       # 통화 125개 전부, mp3 1.9 GB (wav 로 풀면 약 14 GB)
SUBSET=subset10 ./earnings22/install.sh       # 통화 10개, 11 시간
```

전체가 test 다 — 학습 분할은 없다. `metadata.csv` 의 억양 계열(Spanish/Portuguese 31, Asian 28,
English 26, …)은 통화마다 `dataset.yml` 의 `accents` 에 옮긴다.

## 어디서 받나

- **오디오**: [revdotcom/speech-datasets](https://github.com/revdotcom/speech-datasets/tree/main/earnings22)
  의 `media/*.mp3` 는 git-lfs 객체다. `media.githubusercontent.com` 이 파일 하나씩 내주므로 git 도
  git-lfs 도 필요 없다. 표본율이 제각각(8~48 kHz)이라 `convert.py` 가 16 kHz wav 로 한 번 다시 쓴다.
- **구간**: [distil-whisper/earnings22](https://huggingface.co/datasets/distil-whisper/earnings22) 의
  `chunked` 설정. 공식 참조를 문장부호에서 끊고 강제정렬로 통화 안의 시각을 붙인 57,391 구간이다.
  오디오까지 24 GB 인데, `fetch_segments.py` 가 **글자와 시각 열만** 읽어 `data/segments.jsonl` 로
  쓴다(2분 안쪽).

## 공식 저장소의 시각은 쓰지 않는다

공식 참조(`transcripts/nlp_references/*.nlp`)에는 시각이 없다. 강제정렬본
(`force_aligned_nlp_references/*.aligned.nlp`)은 **토큰의 28% 가 시각이 비어 있고**, 문장을 그걸로
만들면 60단어짜리가 1,300초에 걸치는 식으로 엉뚱한 자리에 놓인다. 그래서 위의 구간 표를 쓴다.

## 빼는 구간

- 10초가 넘는데 초당 0.5단어가 안 되는 구간(191개, 1.6 시간) — 정렬 실패거나 거의 무음이다
  (494초에 6단어).
- 200단어가 넘는 구간(1개) — 계약의 상한.
- 오디오 끝을 넘어서 시작하는 구간. `metadata.csv` 의 길이가 실제와 다른 통화가 있다.

몇 개를 뺐는지 변환할 때 찍힌다. `<inaudible>`·`<laugh>`·`<crosstalk>` 같은 태그는 지운다. `uh`·`um`
은 말해진 것이라 남긴다.

## 항목과 세션

구간 하나가 항목 하나이고 `offset`·`duration` 으로 통화 wav 안을 가리킨다. `group` 은 통화이고
순서는 시작 시각이다. 이웃 구간끼리 0.14초쯤 겹친다(구간 표의 여백). 화자 정보는 구간 표에 없어
`speaker` 는 통화 id 다.

## 만들어지는 것

```
earnings22/
  data/metadata.csv           받은 것 (git 에 없다)
  data/segments.jsonl         받은 것 (git 에 없다)
  data/media/<id>.mp3         받은 것 (git 에 없다)
  data/wav16k/<id>.wav        다시 쓴 것 (git 에 없다)
  dataset.yml, manifest.jsonl, alignment.jsonl   생성물
  audio -> data/wav16k        심볼릭 링크
```
