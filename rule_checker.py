"""
규칙 기반 검토 엔진 v3.1
- VML 체크박스 상태를 활용한 정확한 검토 ★
- 13개 규칙 (R01~R13)
"""
import re
from models import ReviewIssue
from config import (
    CORE_EXCESS_RATIO, UNIT_SIZE,
    CAPACITY_UPGRADE_THRESHOLD, CAPACITY_UPGRADE_MULTIPLIER,
    CAPACITY_EXCESS_MULTIPLIER, DISTANCE_EXCESS_RATIO,
    STANDARD_DISCOUNT_RATE,
)


def safe_str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def is_cb_checked(data: dict, cb_name: str) -> bool:
    """
    체크박스 상태 확인 (parser.py의 CHECKBOX_ROW_MAP 키 기준)
    data["_checkboxes"] = {"이설요청_한전": True, "이설요청_영배시스템": True, ...}
    """
    checkboxes = data.get("_checkboxes", {})
    return checkboxes.get(cb_name, False)


def any_cb_checked(data: dict, cb_names: list) -> bool:
    """하나라도 체크된 것이 있으면 True"""
    return any(is_cb_checked(data, n) for n in cb_names)


# ============================================================
# R01: 이설요청 근거 미비
# ============================================================
def check_R01_이설요청근거(data: dict) -> list:
    issues = []
    요청주체 = safe_str(data.get("요청주체")).lower()
    공사유형 = safe_str(data.get("공사유형"))
    공사명 = safe_str(data.get("공사명"))
    공문번호 = safe_str(data.get("이설요청_공문번호"))
    공문시트_존재 = data.get("_doc_photo_has_content", False)

    is_한전 = "한전" in 요청주체

    # R01-1: 한전 요청 — 이설요청 주체(한전/지자체/공공기관/기타) 또는 영배시스템 체크 여부
    # 이설요청 주체에 한전, 지자체, 공공기관, 기타 중 하나라도 체크되어 있으면 충족으로 인정
    이설요청_주체_checkboxes = [
        "이설요청_한전", "이설요청_지자체", "이설요청_공공기관", "이설요청_기타", "이설요청_영배시스템"
    ]
    if is_한전 and not any_cb_checked(data, 이설요청_주체_checkboxes):
        issues.append(ReviewIssue(
            code="R01-1", severity="CRITICAL", category="이설요청근거",
            message="한전 요청 건이나 이설요청 주체(한전/지자체/공공기관/기타) 및 영배시스템 미체크",
            recommendation="이설요청 주체(한전, 지자체, 공공기관, 기타) 또는 영배시스템 중 해당 항목 체크 필요",
        ))

    # R01-2: 한전 이설요청서 체크 여부 (Row 22)
    if is_한전 and not is_cb_checked(data, "이설요청_한전"):
        if 공문시트_존재:
            issues.append(ReviewIssue(
                code="R01-2", severity="INFO", category="이설요청근거",
                message="한전 이설요청서 체크란이 미체크이나, '공문 및 사진' 시트에 내용 존재",
                recommendation="체크리스트의 이설요청서 첨부 체크란을 확인 후 체크 필요",
            ))
        else:
            issues.append(ReviewIssue(
                code="R01-2", severity="CRITICAL", category="이설요청근거",
                message="한전 요청 건이나 이설요청서 미체크 및 '공문 및 사진' 시트 미작성",
                recommendation="이설요청서(공문갑지+세부내역) 첨부 필수",
            ))

    # R01-3: 공문번호 미기입
    placeholder_keywords = ["공문문서번호", "한전공사번호", "SNS"]
    is_placeholder = any(kw in 공문번호 for kw in placeholder_keywords)
    if not 공문번호 or is_placeholder:
        issues.append(ReviewIssue(
            code="R01-3", severity="MAJOR", category="이설요청근거",
            message="이설요청 공문번호 미기입 또는 템플릿 기본값",
            recommendation="실제 공문번호/한전공사번호 기입 필요",
        ))

    # R01-4: 도로확장/지중화 — 지자체 증빙 확인 (Row 23)
    # ★ 한전을 통한 도로확장 요청은 한전 이설요청서로 충분 → 지자체 미체크 허용
    is_도로 = any(kw in 공사유형 + 공사명 for kw in ["도로확장", "지중화", "그린뉴딜"])
    if is_도로 and not is_한전 and not is_cb_checked(data, "이설요청_지자체"):
        issues.append(ReviewIssue(
            code="R01-4", severity="CRITICAL", category="이설요청근거",
            message="도로확장/지중화 관련 공사이나 지자체 문서 미체크",
            recommendation="지자체 공문/시행문서 확인 및 체크",
        ))

    # R01-5: 공사유형 하나도 미선택 (Row 26~30)
    유형_checkboxes = ["공사유형_가", "공사유형_나", "공사유형_다", "공사유형_라", "공사유형_마"]
    if not any_cb_checked(data, 유형_checkboxes):
        issues.append(ReviewIssue(
            code="R01-5", severity="MAJOR", category="이설요청근거",
            message="공사유형이 하나도 선택되지 않음",
            recommendation="해당 공사유형 체크 필수 (가~마 중 택1)",
        ))

    return issues


# ============================================================
# R02: 사업구분 오류
# ============================================================
def check_R02_사업구분(data: dict) -> list:
    issues = []
    공사명 = safe_str(data.get("공사명"))
    사업구분 = safe_str(data.get("사업구분"))
    공사유형 = safe_str(data.get("공사유형"))

    정비_키워드 = ["정비", "위해", "RM", "수목"]
    if any(kw in 공사명 for kw in 정비_키워드) and "지장이설" in 사업구분:
        issues.append(ReviewIssue(
            code="R02-1", severity="CRITICAL", category="사업구분",
            message=f"공사명에 '{next(kw for kw in 정비_키워드 if kw in 공사명)}' 포함인데 사업구분이 '{사업구분}'",
            recommendation="사업구분 확인 — 정비/위해 성격이면 설비정비로 변경 검토",
        ))

    return issues


# ============================================================
# R03: 접속 코어 과다산출
# ============================================================
def check_R03_접속코어(data: dict) -> list:
    issues = []
    cables = data.get("_parsed_cables", [])
    old_enc = data.get("_parsed_old_enclosures", [])
    new_enc = data.get("_parsed_new_enclosures", [])
    all_enc = old_enc + new_enc

    # 망계위별 최대 사용코어 케이블
    tier_max = {}
    for cable in cables:
        tier = cable.network_tier
        if tier not in tier_max or cable.used_cores > tier_max[tier].used_cores:
            tier_max[tier] = cable

    for enc in all_enc:
        for tier, cable in tier_max.items():
            used = cable.used_cores
            if used <= 0:
                continue

            # 지선/가입자/인입: 사용코어 단위
            if tier in ("지선망", "가입자망", "인입구간", "인입망"):
                if enc.splice_cores > used * CORE_EXCESS_RATIO:
                    issues.append(ReviewIssue(
                        code="R03-1", severity="CRITICAL", category="접속코어",
                        message=f"{enc.label}: {tier} {cable.total_cores}C 중 사용코어 {used}C인데 접속 {enc.splice_cores}C (과다)",
                        recommendation=f"사용코어 단위 접속. {used}C 이하로 조정",
                        savings_hint=f"약 {enc.splice_cores - used}C 절감 가능",
                    ))
                    break

            # 간선망: 유니트(12C) 단위
            if tier == "간선망":
                적정 = ((used // UNIT_SIZE) + 1) * UNIT_SIZE
                if enc.splice_cores > 적정 * CORE_EXCESS_RATIO:
                    issues.append(ReviewIssue(
                        code="R03-2", severity="MAJOR", category="접속코어",
                        message=f"{enc.label}: 간선망 사용코어 {used}C, 유니트 기준 {적정}C인데 접속 {enc.splice_cores}C",
                        recommendation=f"유니트(12C) 단위 접속 원칙. {적정}C로 조정",
                    ))
                    break

            # 기간망: 사용률 낮은데 Full 접속
            if tier == "기간망" and cable.total_cores >= 288 and cable.usage_rate < 0.5:
                issues.append(ReviewIssue(
                    code="R03-3", severity="INFO", category="접속코어",
                    message=f"기간망 {cable.total_cores}C 중 사용 {used}C ({cable.usage_rate:.0%}) — Full 접속 시 과다",
                    recommendation="사용률 50% 미만 시 유니트 접속 검토 권장",
                ))
                break

    return issues


# ============================================================
# R04: 케이블 용량 과다선정
# ============================================================
def check_R04_용량과다(data: dict) -> list:
    issues = []
    cables = data.get("_parsed_cables", [])
    공사방안 = safe_str(data.get("공사방안"))
    용량증설 = safe_str(data.get("용량증설_수량"))
    다대화 = safe_str(data.get("다대화_수량"))
    new_cables = data.get("_parsed_new_cables", []) + data.get("_parsed_upgrade_cables", [])

    has_upgrade = 용량증설 and not re.match(r'^\s*0\s*', 용량증설)

    for cable in cables:
        if cable.usage_rate < CAPACITY_UPGRADE_THRESHOLD and has_upgrade:
            issues.append(ReviewIssue(
                code="R04-1", severity="CRITICAL", category="케이블용량",
                message=f"{cable.label}: 사용률 {cable.usage_rate:.0%} ({cable.used_cores}C/{cable.total_cores}C) — 용량증설 기준({CAPACITY_UPGRADE_THRESHOLD:.0%}) 미달인데 증설 설계",
                recommendation=f"사용률 {CAPACITY_UPGRADE_THRESHOLD:.0%} 미만은 증설 불필요. 기존 케이블 활용",
            ))

    for nc in new_cables:
        for cable in cables:
            if nc.network_tier == cable.network_tier and cable.used_cores > 0:
                if nc.total_cores > cable.used_cores * CAPACITY_EXCESS_MULTIPLIER:
                    issues.append(ReviewIssue(
                        code="R04-2", severity="INFO", category="케이블용량",
                        message=f"사용코어 {cable.used_cores}C 대비 신설 {nc.total_cores}C — 구간별 상세 확인 필요",
                        recommendation=(
                            f"ENG시트 기준 사용코어 {cable.used_cores}C의 "
                            f"{CAPACITY_UPGRADE_MULTIPLIER}배={int(cable.used_cores*CAPACITY_UPGRADE_MULTIPLIER)}C 초과이나, "
                            "케이블은 구간별로 신설 용량이 다를 수 있으므로 개황도 이미지에서 "
                            "구간별 케이블 코어수 매핑을 통해 적정성 확인 필요 (AI 이미지 분석 참고)"
                        ),
                    ))

    return issues


# ============================================================
# R05: 단순이설 검토 누락
# ============================================================
def check_R05_단순이설(data: dict) -> list:
    issues = []
    공사방안 = safe_str(data.get("공사방안"))
    절체사유 = safe_str(data.get("절체사유"))
    자가주 = safe_str(data.get("자가주_인허가"))
    전주수량 = safe_str(data.get("전주정보_수량"))

    if "절체" in 공사방안 and not 절체사유:
        issues.append(ReviewIssue(
            code="R05-1", severity="CRITICAL", category="단순이설",
            message="절체이설이나 절체(단순이설 불가) 사유 미기입",
            recommendation="단순이설 불가 사유를 구체적으로 기입",
        ))

    # 자가주 인허가 — 체크박스 기반
    if not is_cb_checked(data, "자가주인허가"):
        issues.append(ReviewIssue(
            code="R05-2", severity="MAJOR", category="단순이설",
            message="자가주 건식 인허가 가능여부가 미확인",
            recommendation="자가주 인허가 가능 여부를 체크하고 불가 시 사유 기입",
        ))

    # 소규모 이설 참고
    try:
        전주수 = int(re.search(r'(\d+)', 전주수량).group(1))
        if 전주수 <= 3:
            issues.append(ReviewIssue(
                code="R05-3", severity="INFO", category="단순이설",
                message=f"이설 대상 전주 {전주수}본 — 소규모로 자가주 건식 단순이설 가능성",
                recommendation="자가주 건식 단순이설 검토 권장",
            ))
    except (TypeError, AttributeError):
        pass

    return issues


# ============================================================
# R06: 케이블종류/다대화
# ============================================================
def check_R06_다대화(data: dict) -> list:
    issues = []
    new_cables = data.get("_parsed_new_cables", [])

    for cable in new_cables:
        if cable.network_tier in ("기간망", "간선망") and "다대화" in cable.label:
            issues.append(ReviewIssue(
                code="R06-1", severity="CRITICAL", category="다대화",
                message=f"{cable.label}: {cable.network_tier} 다대화 — 기간/간선망 다대화 시 리스크 확인",
                recommendation="기간/간선망 다대화는 절체 위험. 야간 작업 가능 여부 확인",
            ))

    return issues


# ============================================================
# R07: 공사비/낙찰가
# ============================================================
def check_R07_공사비(data: dict) -> list:
    issues = []
    공사비_eng = data.get("공사비")
    총계 = data.get("총계")
    낙찰율_raw = data.get("낙찰율")
    총공사비 = data.get("총공사비")
    낙찰공사비 = data.get("낙찰공사비")

    # 낙찰율 검증
    if 낙찰율_raw:
        try:
            rate = float(낙찰율_raw)
            if rate > 1:
                rate = rate / 100
            if rate > STANDARD_DISCOUNT_RATE:
                issues.append(ReviewIssue(
                    code="R07-1", severity="CRITICAL", category="공사비",
                    message=f"낙찰율 {rate:.1%}가 기준({STANDARD_DISCOUNT_RATE:.1%}) 초과",
                    recommendation=f"낙찰율 {STANDARD_DISCOUNT_RATE:.1%} 적용 확인",
                ))
            elif rate < 0.5:
                issues.append(ReviewIssue(
                    code="R07-2", severity="INFO", category="공사비",
                    message=f"낙찰율 {rate:.1%}로 비정상적으로 낮음",
                    recommendation="낙찰율 확인 필요 (입력 오류 가능성)",
                ))
        except (TypeError, ValueError):
            pass

    # ENG시트 공사비 vs 원가계산서 총계 불일치
    try:
        eng_cost = float(공사비_eng)
        cost_total = float(총계)
        if abs(eng_cost - cost_total) > 10000:
            issues.append(ReviewIssue(
                code="R07-3", severity="MAJOR", category="공사비",
                message=f"ENG시트 공사비({eng_cost:,.0f}) ≠ 원가계산서 총계({cost_total:,.0f})",
                recommendation="공사비 금액 일치 여부 확인",
            ))
    except (TypeError, ValueError):
        pass

    return issues


# ============================================================
# R08: 공사명 네이밍
# ============================================================
def check_R08_공사명(data: dict) -> list:
    issues = []
    공사명 = safe_str(data.get("공사명"))
    협력사명 = safe_str(data.get("협력사명"))

    if not 공사명:
        issues.append(ReviewIssue(
            code="R08-1", severity="CRITICAL", category="공사명",
            message="공사명이 미기입",
            recommendation="규정 형식으로 공사명 기입 필수",
        ))
        return issues

    예시_키워드 = ["연도_순수지장", "지역_(공사사유)", "협력사명_TB"]
    if any(kw in 공사명 for kw in 예시_키워드):
        issues.append(ReviewIssue(
            code="R08-2", severity="MAJOR", category="공사명",
            message="공사명이 템플릿 기본값(예시) 그대로 입력됨",
            recommendation="실제 공사 정보로 변경 필요",
        ))

    if not re.match(r'^\d{2}년', 공사명):
        issues.append(ReviewIssue(
            code="R08-3", severity="MINOR", category="공사명",
            message="공사명 선두에 연도 미기입",
            recommendation="'26년_' 형식으로 연도 추가",
        ))

    예시_협력사 = ["BP명 / 설계자 명", "BP명", ""]
    if 협력사명 in 예시_협력사 or not 협력사명:
        issues.append(ReviewIssue(
            code="R08-4", severity="MAJOR", category="공사명",
            message="협력사명이 미기입 또는 템플릿 기본값",
            recommendation="실제 협력사명/설계자명 기입",
        ))

    return issues


# ============================================================
# R09: RM 해소 확인
# ============================================================
def check_R09_RM(data: dict) -> list:
    issues = []
    rm_cbs = ["6차선횡단", "임의횡단_종말주_지상고", "한전위해개소", "코아링케이블링"]

    if not any_cb_checked(data, rm_cbs):
        issues.append(ReviewIssue(
            code="R09-1", severity="INFO", category="RM",
            message="이설 후 RM 항목이 모두 미체크 — 검토 누락 가능성",
            recommendation="6차선횡단, 임의횡단, 배전설비접촉 등 해당사항 체크",
        ))

    return issues


# ============================================================
# R10: 포설거리 적정성
# ============================================================
def check_R10_포설거리(data: dict) -> list:
    issues = []
    케이블_신설 = safe_str(data.get("케이블_신설"))
    케이블_철거 = safe_str(data.get("케이블_철거"))

    if not 케이블_신설 or not 케이블_철거:
        return issues

    신설m = re.search(r'([\d,]+\.?\d*)\s*[mMkK]', 케이블_신설)
    철거m = re.search(r'([\d,]+\.?\d*)\s*[mMkK]', 케이블_철거)

    if 신설m and 철거m:
        신설 = float(신설m.group(1).replace(',', ''))
        철거 = float(철거m.group(1).replace(',', ''))

        if 'K' in 케이블_신설.upper() or 'k' in 케이블_신설:
            신설 *= 1000
        if 'K' in 케이블_철거.upper() or 'k' in 케이블_철거:
            철거 *= 1000

        if 철거 > 10 and 신설 > 철거 * DISTANCE_EXCESS_RATIO:
            ratio = 신설 / 철거
            issues.append(ReviewIssue(
                code="R10-1", severity="MAJOR", category="포설거리",
                message=f"신설거리 {신설:.0f}m가 철거거리 {철거:.0f}m의 {ratio:.1f}배 — 지장구간 외 포설 가능성",
                recommendation="지장이설 범위 내 포설인지 확인. 불필요한 구간 포함 여부 검토",
            ))

    return issues


# ============================================================
# R11: 기입 완전성
# ============================================================
def check_R11_기입완전성(data: dict) -> list:
    issues = []
    필수_항목 = [
        ("공사명", "공사명"), ("사업구분", "사업구분"), ("공사방안", "공사방안"),
        ("요청주체", "요청주체"), ("현장주소", "현장주소"),
        ("공사비", "공사비"), ("전주정보_상세", "전주정보"),
        ("케이블정보_상세", "케이블정보"), ("함체정보_상세", "함체정보"),
    ]

    미기입 = []
    for key, label in 필수_항목:
        v = safe_str(data.get(key))
        if not v or v in ("#REF!", "N/A", "0"):
            미기입.append(label)

    if 미기입:
        issues.append(ReviewIssue(
            code="R11-1", severity="MAJOR", category="기입완전성",
            message=f"필수항목 미기입: {', '.join(미기입)}",
            recommendation="모든 필수항목 기입 확인",
        ))

    return issues


# ============================================================
# R12: 병행공사/TB
# ============================================================
def check_R12_병행공사(data: dict) -> list:
    issues = []
    공사명 = safe_str(data.get("공사명"))

    if "병행" in 공사명 and not is_cb_checked(data, "병행공사"):
        issues.append(ReviewIssue(
            code="R12-1", severity="MAJOR", category="병행공사",
            message="공사명에 '병행' 키워드가 있으나 병행공사 미체크",
            recommendation="병행공사 여부 확인 및 체크",
        ))

    tb_keywords = ["TB", "공동투자", "T&B"]
    if any(kw in 공사명 for kw in tb_keywords) and not is_cb_checked(data, "TB공동투자"):
        issues.append(ReviewIssue(
            code="R12-2", severity="MAJOR", category="병행공사",
            message="공사명에 'TB/공동투자' 키워드가 있으나 미체크",
            recommendation="T&B 공동투자 해당 여부 확인",
        ))

    return issues


# ============================================================
# R13: 원인자 판정
# ============================================================
def check_R13_원인자(data: dict) -> list:
    issues = []
    공사유형 = safe_str(data.get("공사유형"))
    요청주체 = safe_str(data.get("요청주체"))

    is_원인자 = "원인자" in 공사유형 or is_cb_checked(data, "공사유형_라")
    has_판정조서 = is_cb_checked(data, "원인자판정조서")

    if is_원인자 and not has_판정조서:
        issues.append(ReviewIssue(
            code="R13-1", severity="CRITICAL", category="원인자",
            message="원인자 판정 공사이나 판정조서 미첨부",
            recommendation="원인자 비율 판정조서 첨부 필수",
        ))

    return issues


# ============================================================
# 빠른통과 체크
# ============================================================
def check_quick_pass(data: dict) -> list:
    필수_keys = [
        "공사명", "사업구분", "공사방안", "요청주체", "현장주소",
        "공사비", "전주정보_상세", "케이블정보_상세", "함체정보_상세",
    ]
    results = []
    for key in 필수_keys:
        v = safe_str(data.get(key))
        ok = bool(v) and v not in ("#REF!", "N/A")
        results.append({"항목": key, "상태": "✅" if ok else "❌", "값": v[:40] if v else "(빈값)"})
    return results


# ============================================================
# 종합 체크리스트 현황 (시각화용)
# ============================================================
def build_checklist_status(data: dict, rule_results: list) -> list:
    """
    규칙 결과 + 데이터를 종합한 체크리스트 항목 목록 반환.
    각 항목: {"카테고리", "검토항목", "상태", "내용", "규칙코드"}
    상태: "✅ 적합" | "🚨 보완필요" | "⚠️ 확인필요" | "ℹ️ 참고" | "➖ 해당없음"
    """
    rule_map = {}
    for r in rule_results:
        if r.code not in rule_map:
            rule_map[r.code] = r

    def _sev(sev):
        return {"CRITICAL": 4, "MAJOR": 3, "MINOR": 2, "INFO": 1}.get(sev, 0)

    def _worst(codes):
        hits = [rule_map[c] for c in codes if c in rule_map]
        return max(hits, key=lambda r: _sev(r.severity)) if hits else None

    def _mk(cat, item, codes, data_ok, na=False):
        if na:
            return {"카테고리": cat, "검토항목": item, "상태": "➖ 해당없음",
                    "내용": "해당 사항 없음", "규칙코드": "-"}
        issue = _worst(codes)
        if issue:
            sev_label = {"CRITICAL": "🚨 보완필요", "MAJOR": "⚠️ 확인필요",
                         "MINOR": "ℹ️ 참고", "INFO": "ℹ️ 참고"}
            return {"카테고리": cat, "검토항목": item,
                    "상태": sev_label.get(issue.severity, "⚠️ 확인필요"),
                    "내용": issue.message, "규칙코드": issue.code}
        if not data_ok:
            return {"카테고리": cat, "검토항목": item, "상태": "⚠️ 확인필요",
                    "내용": "데이터 미기입 또는 확인 필요", "규칙코드": "-"}
        return {"카테고리": cat, "검토항목": item, "상태": "✅ 적합",
                "내용": "", "규칙코드": "-"}

    요청주체 = safe_str(data.get("요청주체", "")).lower()
    공사유형 = safe_str(data.get("공사유형", ""))
    공사명 = safe_str(data.get("공사명", ""))
    공사방안 = safe_str(data.get("공사방안", ""))
    is_한전 = "한전" in 요청주체
    is_원인자 = "원인자" in 공사유형 or is_cb_checked(data, "공사유형_라")
    is_도로 = any(kw in 공사유형 + 공사명 for kw in ["도로확장", "지중화", "그린뉴딜"])
    is_절체 = "절체" in 공사방안

    # 재활용 케이블 여부: 체크박스 또는 설계상세에서 탐지
    재활용_상세 = safe_str(data.get("절체이설_상세", "")) + safe_str(data.get("용량증설_상세", ""))
    has_재활용_검토 = any(kw in 재활용_상세 for kw in ["재활용", "장조장", "여분", "MSLT"])

    # 병행사업자 여부
    공사명 = safe_str(data.get("공사명", ""))
    is_병행 = is_cb_checked(data, "병행공사") or "병행" in 공사명

    return [
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ① 지장이설 공사 근거 미비
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("① 지장이설 공사 근거 미비", "이설요청 공문번호 기입", ["R01-3"],
            bool(safe_str(data.get("이설요청_공문번호")))),
        _mk("① 지장이설 공사 근거 미비", "공사유형 선택 (가~마 중 택1)", ["R01-5"],
            any_cb_checked(data, ["공사유형_가", "공사유형_나", "공사유형_다", "공사유형_라", "공사유형_마"])),
        _mk("① 지장이설 공사 근거 미비", "이설요청 주체 체크 (한전/지자체/공공기관/기타 또는 영배시스템)", ["R01-1"],
            any_cb_checked(data, ["이설요청_한전", "이설요청_지자체", "이설요청_공공기관", "이설요청_기타", "이설요청_영배시스템"]), na=not is_한전),
        _mk("① 지장이설 공사 근거 미비", "한전 이설요청서 첨부", ["R01-2"],
            is_cb_checked(data, "이설요청_한전"), na=not is_한전),
        _mk("① 지장이설 공사 근거 미비", "지자체 요청 문서 확인 (도로확장·지중화 시)", ["R01-4"],
            is_cb_checked(data, "이설요청_지자체"), na=not is_도로 or is_한전),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ② 사업구분 오류
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("② 사업구분 오류", "사업구분 정확성 (정비/위해/원인자 vs 지장이설)", ["R02-1"],
            bool(safe_str(data.get("사업구분")))),
        _mk("② 사업구분 오류", "공사명과 사업구분 일치 여부", [],
            bool(safe_str(data.get("공사명"))) and bool(safe_str(data.get("사업구분")))),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ③ 접속 코어 과다산출
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("③ 접속 코어 과다산출", "지선·가입자망 사용코어 단위 접속 준수", ["R03-1"],
            "R03-1" not in rule_map),
        _mk("③ 접속 코어 과다산출", "간선망 유니트(12C) 단위 접속 준수", ["R03-2"],
            "R03-2" not in rule_map),
        _mk("③ 접속 코어 과다산출", "기간망 Full 접속 과다 여부", ["R03-3"],
            "R03-3" not in rule_map),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ④ 케이블 용량 과다선정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("④ 케이블 용량 과다선정", "사용률 60% 이상 시 용량증설 기준 충족", ["R04-1"],
            "R04-1" not in rule_map),
        _mk("④ 케이블 용량 과다선정", "신설 케이블 코어수 vs 기설 사용코어 비교", ["R04-2"],
            "R04-2" not in rule_map),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ⑤ 케이블 종류 오선정 (AI 확인 필요)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("⑤ 케이블 종류 오선정", "재활용 케이블 활용 여부 검토 (장조장/여분)", [],
            has_재활용_검토),
        _mk("⑤ 케이블 종류 오선정", "Dry/MSLT 선택 비용 효율성 검토", [], True),
            # → AI/Vision 분석으로만 확인 가능, 자동판단 불가로 항상 적합 처리 (AI가 별도 분석)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ⑥ 케이블 과다거리 포설
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("⑥ 케이블 과다거리 포설", "포설거리 적정 (신설/철거 비율 1.5배 이하)", ["R10-1"],
            "R10-1" not in rule_map),
        _mk("⑥ 케이블 과다거리 포설", "공문 지장구간 외 추가 포설 사유 기재", [],
            bool(safe_str(data.get("케이블_신설")))),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ⑦ 다대화 대상 오선정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("⑦ 다대화 대상 오선정", "기간/간선망 다대화 절체 위험 검토", ["R06-1"],
            "R06-1" not in rule_map),
        _mk("⑦ 다대화 대상 오선정", "폭탄함체 해소 목적 다대화 적정성", [], True),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ⑧ 단순이설 대상 절체이설
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("⑧ 단순이설 대상 절체이설", "절체이설 불가 사유 기입 (6가지 Case 해당)", ["R05-1"],
            bool(safe_str(data.get("절체사유"))), na=not is_절체),
        _mk("⑧ 단순이설 대상 절체이설", "자가주 건식 인허가 가능 여부 확인", ["R05-2"],
            is_cb_checked(data, "자가주인허가")),
        _mk("⑧ 단순이설 대상 절체이설", "소규모 이설 — E장주 취부·자가주 건식 검토", ["R05-3"], True),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ⑩ 원인자 대상 지장이설 설계
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("⑩ 원인자 대상 지장이설", "원인자 판정조서 첨부", ["R13-1"],
            is_cb_checked(data, "원인자판정조서"), na=not is_원인자),
        _mk("⑩ 원인자 대상 지장이설", "원인자 전환 여부 및 설계 적정성", [], True),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ⑪ 기설 시설물 미사용 (AI/Vision 확인 필요)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("⑪ 기설 시설물 미사용", "기설루트 사용 여부 (체크박스 확인)", [],
            is_cb_checked(data, "기설통신주관로") or is_cb_checked(data, "기설루트사용")),
        _mk("⑪ 기설 시설물 미사용", "기설 관로·맨홀·함체 활용 가능성 검토 — Vision AI 확인", [],
            True),  # AI 분석 필요, 자동판단 불가

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ⑫ 기설 시설물 철거설계 (AI/Vision 확인 필요)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("⑫ 기설 시설물 철거설계", "함체·전주 철거 수량 기입", [],
            bool(safe_str(data.get("함체_철거"))) or bool(safe_str(data.get("케이블_철거")))),
        _mk("⑫ 기설 시설물 철거설계", "케이블 철거 품 포함 여부 — Vision AI 확인", [], True),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ⑬ 실사비·설계비 오적용 (AI 확인 필요)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("⑬ 실사비·설계비 오적용", "공사비 낙찰율 기준 적합 (≤74.9%)", ["R07-1", "R07-2"],
            "R07-1" not in rule_map),
        _mk("⑬ 실사비·설계비 오적용", "ENG시트 ↔ 원가계산서 공사비 일치", ["R07-3"],
            "R07-3" not in rule_map),
        _mk("⑬ 실사비·설계비 오적용", "탐지비·측량비 산출 근거 적정성 — AI 확인", [], True),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ⑭ 타사주관 설계 검토 미비
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("⑭ 타사주관 설계 검토 미비", "병행공사 여부 확인", ["R12-1", "R12-2"],
            "R12-1" not in rule_map and "R12-2" not in rule_map),
        _mk("⑭ 타사주관 설계 검토 미비", "TB 공동투자 확인", ["R12-2"],
            "R12-2" not in rule_map),
        _mk("⑭ 타사주관 설계 검토 미비", "병행구간 FC공수·SKT 미참여구간 확인 — AI 확인",
            [], True, na=not is_병행),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ⑮ 관로 굴착공사 기준 위배 (관로공사 시만 해당)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("⑮ 관로 굴착공사 기준 위배", "FC공수 공정집계표↔도면 일치 여부 — AI 확인", [], True),
        _mk("⑮ 관로 굴착공사 기준 위배", "굴착폭·토피·환토재·관경 기준 준수 — AI 확인", [], True),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ⑯ 현장실사 내용 불일치
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("⑯ 현장실사 내용 불일치", "GIS 불일치 항목 체크 여부 (관로·전주·케이블·함체)",
            [], is_cb_checked(data, "GIS_불일치_관로전주") or is_cb_checked(data, "GIS_불일치_케이블함체")),
        _mk("⑯ 현장실사 내용 불일치", "GIS 특이사항 기재 여부",
            [], is_cb_checked(data, "GIS_특이사항")),
        _mk("⑯ 현장실사 내용 불일치", "GIS↔개황도↔현장사진 정합성 — Vision AI 확인", [], True),

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 체크 ⑰ 기타 / 체크 ⑱ 특이사항 없음 (기본정보)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _mk("⑰ 기타·기본정보", "공사명 기입 및 네이밍룰 준수", ["R08-1", "R08-2", "R08-3"],
            bool(safe_str(data.get("공사명")))),
        _mk("⑰ 기타·기본정보", "협력사명/설계자 기입", ["R08-4"],
            bool(safe_str(data.get("협력사명")))),
        _mk("⑰ 기타·기본정보", "현장주소 기입", [],
            bool(safe_str(data.get("현장주소")))),
        _mk("⑰ 기타·기본정보", "이설 후 RM 항목 검토 (6차선·임의횡단·배전접촉 등)", ["R09-1"],
            any_cb_checked(data, ["6차선횡단", "임의횡단_종말주", "배전설비접촉", "코어링_케이블링"])),
    ]


# ============================================================
# 전체 실행
# ============================================================
def run_all_rules(data: dict) -> list:
    all_issues = []
    rules = [
        check_R01_이설요청근거,
        check_R02_사업구분,
        check_R03_접속코어,
        check_R04_용량과다,
        check_R05_단순이설,
        check_R06_다대화,
        check_R07_공사비,
        check_R08_공사명,
        check_R09_RM,
        check_R10_포설거리,
        check_R11_기입완전성,
        check_R12_병행공사,
        check_R13_원인자,
    ]

    for rule_fn in rules:
        try:
            all_issues.extend(rule_fn(data))
        except Exception as e:
            all_issues.append(ReviewIssue(
                code="ERR", severity="INFO", category="시스템",
                message=f"규칙 {rule_fn.__name__} 실행 오류: {str(e)[:80]}",
            ))

    return all_issues
