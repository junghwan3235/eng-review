"""
검토 리포트 생성 모듈
"""
from datetime import datetime
from parser import safe_str


def severity_emoji(sev: str) -> str:
    return {
        "CRITICAL": "🚨",
        "MAJOR": "⚠️",
        "MINOR": "💡",
        "INFO": "ℹ️",
    }.get(sev, "❓")


def severity_label(sev: str) -> str:
    return {
        "CRITICAL": "심각",
        "MAJOR": "주요",
        "MINOR": "경미",
        "INFO": "참고",
    }.get(sev, sev)


def generate_report(
    data: dict,
    rule_results: list,
    quick_results: list,
    ai_result: dict = None,
) -> str:
    """Markdown 형식의 검토 리포트 생성"""

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    공사명 = safe_str(data.get("공사명"))
    사업구분 = safe_str(data.get("사업구분"))
    공사방안 = safe_str(data.get("공사방안"))
    공사비 = safe_str(data.get("공사비"))

    # 심각도별 카운트
    counts = {"CRITICAL": 0, "MAJOR": 0, "MINOR": 0, "INFO": 0}
    for r in rule_results:
        counts[r.severity] = counts.get(r.severity, 0) + 1

    total = len(rule_results)
    판정 = "적합"
    if counts["CRITICAL"] > 0:
        판정 = "🔴 보완요청"
    elif counts["MAJOR"] > 0:
        판정 = "🟡 확인필요"
    else:
        판정 = "🟢 적합"

    lines = []
    lines.append(f"# 지장이설 설계검토 결과 리포트")
    lines.append(f"")
    lines.append(f"**검토일시**: {now}")
    lines.append(f"**검토도구**: 지장이설 설계검토 Agent v3.0")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## 1. 공사 개요")
    lines.append(f"")
    lines.append(f"| 항목 | 내용 |")
    lines.append(f"|------|------|")
    lines.append(f"| 공사명 | {공사명} |")
    lines.append(f"| 사업구분 | {사업구분} |")
    lines.append(f"| 공사방안 | {공사방안} |")
    lines.append(f"| 요청주체 | {safe_str(data.get('요청주체'))} |")
    lines.append(f"| 공사비 | {공사비} |")
    lines.append(f"| 현장주소 | {safe_str(data.get('현장주소'))} |")
    lines.append(f"")

    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## 2. 검토 결과 요약")
    lines.append(f"")
    lines.append(f"### 종합 판정: {판정}")
    lines.append(f"")
    lines.append(f"| 심각도 | 건수 |")
    lines.append(f"|--------|------|")
    lines.append(f"| 🚨 심각(CRITICAL) | {counts['CRITICAL']}건 |")
    lines.append(f"| ⚠️ 주요(MAJOR) | {counts['MAJOR']}건 |")
    lines.append(f"| 💡 경미(MINOR) | {counts['MINOR']}건 |")
    lines.append(f"| ℹ️ 참고(INFO) | {counts['INFO']}건 |")
    lines.append(f"| **합계** | **{total}건** |")
    lines.append(f"")

    # 3. 지적사항 상세
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## 3. 🔴 강화검토 지적사항 상세")
    lines.append(f"")

    if not rule_results:
        lines.append(f"✅ 자동 규칙 검토에서 지적사항이 발견되지 않았습니다.")
    else:
        # 카테고리별 그룹핑
        categories = {}
        for r in rule_results:
            cat = r.category or "기타"
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(r)

        for cat, items in categories.items():
            lines.append(f"### [{cat}]")
            lines.append(f"")
            for r in items:
                emoji = severity_emoji(r.severity)
                lines.append(f"#### {emoji} {r.code} — {r.message}")
                lines.append(f"")
                lines.append(f"- **심각도**: {severity_label(r.severity)}")
                lines.append(f"- **권고사항**: {r.recommendation}")
                if r.savings_hint:
                    lines.append(f"- **절감 포인트**: {r.savings_hint}")
                if r.reference:
                    lines.append(f"- **근거 규정**: {r.reference}")
                lines.append(f"")

    # 4. 빠른통과
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## 4. 🟢 빠른통과 항목 (기입 여부)")
    lines.append(f"")
    lines.append(f"| 항목 | 상태 | 값 |")
    lines.append(f"|------|------|-----|")
    for item in quick_results:
        lines.append(f"| {item['항목']} | {item['상태']} | {item.get('값', '')} |")
    lines.append(f"")

    # 5. AI 검토 의견
    if ai_result:
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"## 5. 🤖 AI 보조 검토 의견")
        lines.append(f"")

        if ai_result.get("comprehensive"):
            lines.append(f"### 종합 검토")
            lines.append(f"")
            lines.append(ai_result["comprehensive"])
            lines.append(f"")

        if ai_result.get("comparison"):
            lines.append(f"### 개황도 전/후 비교 분석")
            lines.append(f"")
            lines.append(ai_result["comparison"])
            lines.append(f"")

        if ai_result.get("image_analyses"):
            lines.append(f"### 이미지별 분석")
            lines.append(f"")
            for analysis in ai_result["image_analyses"]:
                lines.append(analysis)
                lines.append(f"")

    # 6. 면책
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## 참고사항")
    lines.append(f"")
    lines.append(f"- 본 검토는 AI 자동 검토 결과이며, 최종 판단은 검토자가 수행합니다.")
    lines.append(f"- GIS 데이터 교차 검증이 미포함되어 현장 확인이 필요할 수 있습니다.")
    lines.append(f"- 이미지 분석은 OpenAI Vision API 기반이며, 판독 정확도 한계가 있습니다.")
    lines.append(f"- 규칙 기반 검토의 임계값은 지속적으로 보정 중입니다.")
    lines.append(f"")

    return "\n".join(lines)
