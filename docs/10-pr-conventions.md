# 10. Pull Request 관례

이 저장소의 PR 본문은 **항상** 아래 세 섹션만 사용한다. 드래프트·정식 PR 모두 동일하다.

```markdown
### Summary
목적·목표와 전체 변경을 1~3문장으로 요약한다.

### Changes
구체적인 변경사항을 bullet로 나열한다.

### Notes
비고(로컬 검증 방법, 범위 밖 항목, 운영 주의 등)를 적는다.
```

## 규칙

- `## Test plan` 등 다른 섹션 헤딩은 쓰지 않는다. 검증 안내는 **Notes**에 넣는다.
- 구현 중간에도 드래프트 PR을 열고, 커밋·push 후 Summary/Changes/Notes를 갱신한다.
- Changes는 진행에 따라 bullet을 누적한다.

다음: [목차로](README.md)
