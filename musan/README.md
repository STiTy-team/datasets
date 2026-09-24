# MUSAN

잡음(noise)·음악(music)·말소리(speech)를 모은 **잡음 합성용** 코퍼스([OpenSLR 17](https://www.openslr.org/17/),
CC BY 4.0, 하위 폴더마다 LICENSE 가 따로 있다). 전사가 없어 그 자체로는 데이터셋이 아니다 —
**이미 만든 데이터셋에 섞어서** 잡음 조건의 새 데이터셋을 만든다.

```bash
./musan/install.sh                                         # 받기만: noise + music
SOURCE=fleurs/en_us ./musan/install.sh                     # noise 를 0/5/10/15 dB 로 -> musan/fleurs_en_us.noise-snr{0,5,10,15}/
SOURCE=zeroth KIND=music SNRS="5 10" ./musan/install.sh
KINDS="noise music speech" ./musan/install.sh              # babble 용 말소리까지 (60 시간)
uv run python musan/convert.py --source ami --kind noise --snr 10
```

| 종류 | 내용 | 크기 |
|---|---|---|
| `noise` | free-sound, sound-bible 의 생활 잡음(기계음, 박수, 문소리…) 929개, 6 시간 | 약 0.9 GB |
| `music` | fma, jamendo, hd-classical 등, 42 시간 | 약 5 GB |
| `speech` | librivox, 미국 정부 기록 낭독, 60 시간 | 약 7 GB |

## 11 GB tar 를 흘려 받는다

OpenSLR 은 tar.gz 하나만 준다. `install.sh` 는 그걸 디스크에 내려놓지 않고 흘려 받으며 `KINDS` 에 든
폴더만 푼다. 대신 **중간에 끊기면 처음부터** 다시 받는다(5~8 MB/s 에서 25~40분). 느리면
`MUSAN_URL=https://openslr.elda.org/resources/17/musan.tar.gz` 처럼 미러를 쓴다.

## 섞는 방법

`convert.py --source <데이터셋> --kind <종류> --snr <dB>` 는 원본 manifest 가 가리키는 **wav 마다**
MUSAN 을 깔아 다시 쓴다. 단어도, 시각도, 항목 구간도 그대로라 manifest·`alignment.jsonl`·스펙을
그대로 옮긴다 — 정렬을 다시 돌리지 않는다. 회의·강연처럼 긴 wav 하나에 `offset` 으로 구간이 걸린
데이터셋도 그대로 된다.

- **잡음 트랙**: 그 종류의 MUSAN 파일을 무작위 지점부터 이어 붙여 wav 길이를 채운다. 무엇을 고를지는
  `--seed` 와 wav 의 경로로 정해져서 다시 만들어도 같다.
- **SNR 기준**: 발화의 활성 구간 세기 — 20 ms 프레임 중 가장 센 것에서 30 dB 안쪽인 프레임의 평균
  세기. 짧은 클립 앞뒤의 무음이나 회의의 빈 구간이 SNR 을 부풀리지 않게 한다. 테스트에서 잰 SNR 이
  지정값과 ±0.01 dB 안이었다.
- **클리핑**: 섞은 결과가 넘치면 말과 잡음을 **함께** 줄인다 — SNR 은 그대로다.

MUSAN 에는 공식 train/test 구분이 없다. 문헌마다 따로 정한다(0/5/10/15 dB 가 흔하다). 여기서는
모든 파일을 쓰고, 시드와 경로로 고정한다. 학습에 MUSAN 을 쓴 모델을 잴 때는 이 점을 감안한다.

## 만들어지는 것

```
musan/
  data/musan/{noise,music,speech}/**/*.wav     받은 것 (git 에 없다)
  data/mixed/<이름>/...                         섞은 wav (git 에 없다)
  <원본 이름>.<종류>-snr<dB>[-seed<n>]/          섞은 데이터셋 (git 에 없다)
    dataset.yml     원본 스펙 + musan: {source, kind, snr_db, seed}
    manifest.jsonl  원본 그대로
    alignment.jsonl 원본 그대로 (있으면)
    audio -> data/mixed/<이름>
```
