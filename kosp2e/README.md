# kosp2e

한국어 음성에 영어 번역을 붙인 ko→en 음성번역 코퍼스([warnikchow/kosp2e](https://github.com/warnikchow/kosp2e),
Interspeech 2021). 한국어를 **소스로** 하는 음성번역 참조가 있는 몇 안 되는 공개 코퍼스다.

```bash
./kosp2e/install.sh                   # test: 2,320 발화
PART=dev ./kosp2e/install.sh
```

네 코퍼스를 모은 것이라 성격이 섞여 있다.

| 코퍼스 | 내용 | test 발화 | 라이선스 |
|---|---|---|---|
| `zeroth` | 뉴스 문장 낭독 | 461 | CC BY 4.0 |
| `kss` | 한 화자 낭독 + 여러 화자 재녹음 | 512 | CC BY-NC-SA 4.0 |
| `stylekqc` | 구어체 질문·명령 | 720 | CC BY-SA 4.0 |
| `covid` | 코로나 시기 감정 서술 | 627 | CC BY-NC-SA 4.0 |

KSS 와 Covid-ED 는 비상업·학술용이다. 저장소 README 의 StyleKQC 개수(400/800)는 실제
분할 파일(480/720)과 다르다. 여기 적은 것은 파일에서 센 값이다.

## 한국어 전사가 없다

오디오와 영어 번역은 공개돼 있지만, **한국어 전사는 저자에게 신청해야 받는다**
([신청 양식](https://docs.google.com/forms/d/1UTpOrKIWK9uzngh7eIm-3oAp5b5vTdBj4ZapHj8cyBI/edit)).
그래서 `dataset.yml` 이 `provides.transcript: false` 를 선언하고, `verify()` 는 빈 전사를
문제 삼지 않는다. 전사를 받으면 `convert.py` 에 붙이면 된다.

## 17 GB zip 에서 필요한 wav 만 꺼낸다

오디오는 Dropbox 의 zip 하나(17 GB, wav 11만 개)에 다 들어 있고, 분할별로 나뉜 파일이 없다.
`install.sh` 는 zip 을 통째로 받지 않고, [remotezip](https://github.com/gtsystem/python-remotezip)
으로 zip 의 목차만 읽은 다음 분할 목록(`split/<corpus>_<part>.xlsx`)에 있는 wav 만 HTTP range
요청으로 하나씩 꺼낸다. test 는 484 MB 다.

**하나씩 받는다.** 16개를 동시에 요청했더니 Dropbox 가 range 요청을 거부하기 시작했다.
test 전체가 약 1시간 걸린다(2,000개에 53분). 중간에 끊겨도 다시 돌리면 받은 것은 건너뛰고 이어서 받는다.

## 항목과 세션

발화 하나가 항목 하나이고 `group` 도 그 발화다 — **항목마다 새 세션**이다. `speaker` 에는
화자 대신 코퍼스 이름을 넣었다 — 분할 파일에 화자 정보가 없다.

오디오는 이미 16 kHz mono PCM16 wav 라 디코딩 없이 링크만 건다.

## 만들어지는 것

```
kosp2e/
  data/<corpus>_<part>.xlsx        받은 것 (git 에 없다)
  data/<corpus>/<id>.wav           받은 것 (git 에 없다)
  dataset.yml                      생성물
  manifest.jsonl                   생성물
  audio -> data                    심볼릭 링크
```
