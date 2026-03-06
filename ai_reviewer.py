"""
AI 보조 검토 모듈 v3.2
- 행정도 범례 지식 기반 이미지 분석
- 시트 전체 스냅샷 우선 / 개별이미지 중복제거 fallback
- 공사 이해 요약 (사용자 검증용) — 항상 생성
"""
import base64
import hashlib
import re
from typing import Optional, List, Dict
from openai import OpenAI
from config import (
    VISION_SYSTEM_PROMPT, VISION_COMPARE_PROMPT,
    COMPREHENSIVE_REVIEW_PROMPT, LEGEND_KNOWLEDGE,
    DESIGN_REVIEW_CRITERIA, VISION_INTEGRATED_PROMPT,
)
from parser import safe_str


def get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def encode_image_base64(image_data: bytes) -> str:
    return base64.b64encode(image_data).decode("utf-8")


def detect_image_type(filename: str) -> str:
    ext = filename.lower().split(".")[-1] if "." in filename else "png"
    return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "bmp": "image/bmp", "webp": "image/webp"
            }.get(ext, "image/png")


def _build_design_context(d: dict) -> str:
    # 체크박스에서 선택된 이설루트 방법 추출
    cb = d.get("_checkboxes", {})
    route_methods = []
    if cb.get("기설통신주관로"): route_methods.append("기설 통신주/관로 루트사용")
    if cb.get("병행관로전주"): route_methods.append("병행 관로/전주 신설")
    if cb.get("단독관로전주"): route_methods.append("단독 관로/전주 신설")
    if cb.get("한전주이설"): route_methods.append("한전주 이설")
    route_선택 = ", ".join(route_methods) if route_methods else "미선택"

    # 설계 신설정보 요약
    design_items = []
    절체수량 = safe_str(d.get("절체이설_수량"))
    if 절체수량 and not re.match(r'^\s*0\s*', 절체수량):
        design_items.append(f"절체이설 {절체수량}")
    용량수량 = safe_str(d.get("용량증설_수량"))
    if 용량수량 and not re.match(r'^\s*0\s*', 용량수량):
        design_items.append(f"용량증설 {용량수량}")
    다대화수량 = safe_str(d.get("다대화_수량"))
    if 다대화수량 and not re.match(r'^\s*0\s*', 다대화수량):
        design_items.append(f"다대화 {다대화수량}")

    return f"""설계 맥락:
- 공사명: {safe_str(d.get('공사명'))}
- 사업구분: {safe_str(d.get('사업구분'))} / 공사유형: {safe_str(d.get('공사유형'))}
- 공사방안: {safe_str(d.get('공사방안'))} / 요청주체: {safe_str(d.get('요청주체'))}
- 현장주소: {safe_str(d.get('현장주소'))}
- 전주정보: {safe_str(d.get('전주정보_상세'))}
- 케이블정보: {safe_str(d.get('케이블정보_상세'))}
- 이설전 루트: {safe_str(d.get('이설전_루트구성'))}
- 이설후 루트: {safe_str(d.get('이설후_루트구성'))}
- 케이블 신설: {safe_str(d.get('케이블_신설'))} / 철거: {safe_str(d.get('케이블_철거'))}
- 함체 신설: {safe_str(d.get('함체_신설'))} / 철거: {safe_str(d.get('함체_철거'))}
- 절체사유: {safe_str(d.get('절체사유'))}
- ★ 이설루트 방법: {route_선택}
- ★ 기설루트사용 상세: {safe_str(d.get('기설루트사용_상세'))}
- ★ 한전주이설 상세: {safe_str(d.get('한전주이설_상세'))}
- ★ 설계신설 구성: {', '.join(design_items) if design_items else '없음'}
- ★ 절체이설 상세: {safe_str(d.get('절체이설_상세'))}
- ★ 용량증설 상세: {safe_str(d.get('용량증설_상세'))}
- ★ 다대화 상세: {safe_str(d.get('다대화_상세'))}
- ★ 함체신설 상세: {safe_str(d.get('함체신설_상세'))}"""


# ============================================================
# 스냅샷 단일 분석 (범례 지식 포함)
# ============================================================
def analyze_single_image(api_key, image_data, filename, design_context, model="gpt-4o"):
    """행정도 스냅샷 1장 → Vision API 분석"""
    client = get_client(api_key)
    b64 = encode_image_base64(image_data)
    mime = detect_image_type(filename)

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": f"{_build_design_context(design_context)}\n\n위 설계 맥락을 참고하여 아래 개황도를 분석해주세요."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}},
                ]},
            ],
            max_tokens=2000, temperature=0.1,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"⚠️ Vision API 오류: {e}"


# ============================================================
# ★ 개별 이미지 배치 분석 (스냅샷 없을 때 fallback)
# ============================================================

INDIVIDUAL_IMAGE_SYSTEM = f"""당신은 통신 선로(케이블, 전주, 함체) 설계 검토 전문가입니다.

⚠️ **중요**: 지금 보는 이미지는 행정도 Excel 시트에서 추출된 **개별 임베디드 이미지**입니다.
행정도 전체 뷰(지도+선로+심볼+텍스트+사진이 합쳐진 복합 도면)가 아니라
시트에 삽입된 **개별 사진/지도 조각**입니다.

따라서:
- 선로 심볼(빨간점선=신설, 검정실선=철거 등)이 보이면 범례에 따라 해석
- 전주/함체 심볼이 보이면 색상/형태로 구분하여 기술
- 텍스트가 보이면 반드시 읽어서 기록 (케이블번호, 코어수, 거리, 메모 등)
- 현장사진이면 도로환경, 전주상태, 시설물 상황을 기술
- **확실히 보이는 것만 기술**, 추정은 '확인필요'로 표시

{LEGEND_KNOWLEDGE}"""


def analyze_images_batch(api_key, images, sheet_name, design_context, model="gpt-4o", max_images=6):
    """한 시트의 여러 이미지를 한 번에 보내서 종합 분석"""
    if not images:
        return ""
    client = get_client(api_key)
    selected = sorted(images, key=lambda x: len(x.data), reverse=True)[:max_images]

    content_parts = [{"type": "text", "text": (
        f"## {sheet_name} 시트에서 추출된 {len(selected)}장의 이미지입니다.\n\n"
        f"{_build_design_context(design_context)}\n\n"
        f"이 이미지들은 '{sheet_name}' 시트에 삽입된 개별 이미지입니다.\n"
        "각 이미지에서:\n"
        "1. 지도/도면: 선로 경로, 심볼(범례 참고), 텍스트 레이블 읽기\n"
        "2. 현장사진: 도로환경, 전주/케이블 상태, 위해요소\n"
        "3. 텍스트/표: 정보 추출\n\n"
        "★ 이미지별로 구분하여 분석 결과를 작성해주세요."
    )}]

    for i, img in enumerate(selected, 1):
        b64 = encode_image_base64(img.data)
        mime = detect_image_type(img.filename)
        content_parts.append({"type": "text", "text": f"\n--- 이미지 {i}/{len(selected)}: {img.filename} ({len(img.data):,}bytes) ---"})
        content_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}})

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": INDIVIDUAL_IMAGE_SYSTEM},
                {"role": "user", "content": content_parts},
            ],
            max_tokens=2500, temperature=0.1,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"⚠️ Vision API 배치 분석 오류: {e}"


# ============================================================
# 전/후 비교 분석
# ============================================================
def compare_before_after(api_key, before_image, before_fn, after_image, after_fn, design_context, model="gpt-4o"):
    client = get_client(api_key)

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": VISION_COMPARE_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": f"{_build_design_context(design_context)}\n\n아래 두 이미지를 비교 분석해주세요.\n첫 번째 = 개황도(전), 두 번째 = 개황도(후)"},
                    {"type": "image_url", "image_url": {"url": f"data:{detect_image_type(before_fn)};base64,{encode_image_base64(before_image)}", "detail": "high"}},
                    {"type": "image_url", "image_url": {"url": f"data:{detect_image_type(after_fn)};base64,{encode_image_base64(after_image)}", "detail": "high"}},
                ]},
            ],
            max_tokens=2500, temperature=0.1,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"⚠️ 비교 분석 오류: {e}"


# ============================================================
# ★★★ 통합 3장 분석 (GIS + 개황도(전) + 개황도(후))
# ============================================================
def analyze_integrated_images(
    api_key, gis_image, before_image, after_image,
    design_context, model="gpt-4o"
):
    """GIS + 개황도(전) + 개황도(후)를 한꺼번에 전달하여 통합 분석.
    파싱된 ENG시트 데이터도 함께 전달하여 교차검증."""
    client = get_client(api_key)
    ctx = _build_design_context(design_context)

    content_parts = [
        {"type": "text", "text": (
            f"{ctx}\n\n"
            "위 설계서 데이터(ENG시트 파싱 결과)를 참고하여 아래 3장의 이미지를 통합 분석해주세요.\n"
            "이미지 순서: ① 작업 전 GIS → ② 개황도(전) → ③ 개황도(후)"
        )},
    ]

    # GIS
    if gis_image:
        content_parts.append({"type": "text", "text": "\n--- ① 작업 전 GIS ---"})
        content_parts.append({"type": "image_url", "image_url": {
            "url": f"data:image/png;base64,{encode_image_base64(gis_image)}",
            "detail": "high"
        }})

    # 개황도(전)
    if before_image:
        content_parts.append({"type": "text", "text": "\n--- ② 개황도(전) — 이설 전 현황 ---"})
        content_parts.append({"type": "image_url", "image_url": {
            "url": f"data:image/png;base64,{encode_image_base64(before_image)}",
            "detail": "high"
        }})

    # 개황도(후)
    if after_image:
        content_parts.append({"type": "text", "text": "\n--- ③ 개황도(후) — 이설 후 설계 ---"})
        content_parts.append({"type": "image_url", "image_url": {
            "url": f"data:image/png;base64,{encode_image_base64(after_image)}",
            "detail": "high"
        }})

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": VISION_INTEGRATED_PROMPT},
                {"role": "user", "content": content_parts},
            ],
            max_tokens=4000, temperature=0.1,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"⚠️ 통합 분석 오류: {e}"


# ============================================================
# 증빙 사진 분석
# ============================================================
def analyze_evidence_photo(api_key, image_data, filename, photo_type="일반", model="gpt-4o"):
    client = get_client(api_key)
    prompts = {
        "영배시스템": "한전 영업배전시스템 화면입니다. 공사번호, 등록상태, 구간정보를 추출하세요.",
        "이설요청서": "이설요청서입니다. 요청주체, 사유, 위치, 범위를 추출하세요.",
        "현장사진": "통신 선로 현장 사진입니다. 시설물, 위해요소, 자가주 건식 가능성을 기술하세요.",
        "판정조서": "원인자 판정조서입니다. 원인자, 부담비율, 사유를 추출하세요.",
        "일반": "통신 선로 설계 검토에 관련된 정보를 추출해주세요.",
    }
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompts.get(photo_type, prompts["일반"])},
                {"type": "image_url", "image_url": {"url": f"data:{detect_image_type(filename)};base64,{encode_image_base64(image_data)}", "detail": "high"}},
            ]}],
            max_tokens=1500, temperature=0.1,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"⚠️ 오류: {e}"


# ============================================================
# 텍스트 기반 종합 검토
# ============================================================
def comprehensive_review(api_key, parsed_data, rule_results, model="gpt-4o", expert_notes: str = ""):
    client = get_client(api_key)
    rule_lines = [f"[{r.severity}] {r.code}: {r.message}" for r in rule_results]
    rule_text = "\n".join(rule_lines) if rule_lines else "자동 검토 결과 지적사항 없음"

    # 검토담당자 발췌 문제점 섹션 (있을 때만 포함)
    expert_section = ""
    if expert_notes and expert_notes.strip():
        expert_section = f"""
=== ★★★ 검토담당자 발췌 문제점 (최우선 분석 대상) ===
아래는 실제 검토 담당자가 직접 발췌한 문제점입니다.
이 내용을 가장 우선적으로 검토 의견에 반영하고, 각 문제점마다 설계 데이터와 교차 검증하여
구체적 근거와 보완 방향을 함께 제시하세요. 단순히 재나열하지 말고 심층 분석을 하세요.

{expert_notes.strip()}

=== 검토담당자 발췌 내용 끝 ===
"""

    info = f"""{expert_section}=== 설계서 요약 ===
공사명: {safe_str(parsed_data.get('공사명'))}
사업구분: {safe_str(parsed_data.get('사업구분'))} / 공사방안: {safe_str(parsed_data.get('공사방안'))}
공사유형: {safe_str(parsed_data.get('공사유형'))} / 요청주체: {safe_str(parsed_data.get('요청주체'))}
공사비: {safe_str(parsed_data.get('공사비'))} / 절체사유: {safe_str(parsed_data.get('절체사유'))}

=== 기설정보 ===
전주: {safe_str(parsed_data.get('전주정보_수량'))} - {safe_str(parsed_data.get('전주정보_상세'))}
케이블: {safe_str(parsed_data.get('케이블정보_수량'))} - {safe_str(parsed_data.get('케이블정보_상세'))}
함체: {safe_str(parsed_data.get('함체정보_수량'))} - {safe_str(parsed_data.get('함체정보_상세'))}

=== 신설정보 ===
절체이설: {safe_str(parsed_data.get('절체이설_수량'))} - {safe_str(parsed_data.get('절체이설_상세'))}
케이블 신설: {safe_str(parsed_data.get('케이블_신설'))} / 철거: {safe_str(parsed_data.get('케이블_철거'))}

=== 자동 규칙 검토 결과 ===
{rule_text}"""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": COMPREHENSIVE_REVIEW_PROMPT},
                {"role": "user", "content": info},
            ],
            max_tokens=2000, temperature=0.2,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"⚠️ 종합 검토 오류: {e}"


# ============================================================
# ★★★ 공사 이해 요약 (사용자 검증용) — 항상 생성
# ============================================================

CONSTRUCTION_UNDERSTANDING_PROMPT = f"""당신은 통신 선로 설계 검토 전문가입니다.
아래 범례를 숙지한 후, 제공된 이미지에서 **눈에 보이는 정보만** 정확하게 추출·정리해주세요.
사용자가 "AI가 이미지를 제대로 이해했는지" 검증하기 위한 자료입니다.
**이미지에서 직접 읽은/본 내용**만 기술하세요. 추정은 (추정)으로 표시.

{LEGEND_KNOWLEDGE}

## 아래 형식으로 정리 (이미지에서 직접 읽은 내용만!)

### 📍 1. 공사 위치/구간
- 국소명 / 주소 / 구간거리 (텍스트에서 읽은 것)

### 🔧 2. 기설 시설물 (노란 심볼 + 텍스트)
- 기설함체: [번호, 위치] (예: [기설함체#1] 1898RTE004/IP주함체 접속9C)
- 기설케이블: [번호, 코어수, 거리] (예: 48C =2282= 철거 239m)
- 기설전주: 노란C 심볼 수 / 한전주·자가주 구분

### 🆕 3. 신설 계획 (빨간 심볼 + 빨간점선)
- 신설케이블 루트: 빨간점선 경로 설명
- 신설전주: 빨간C 위치/수량
- 신설함체: 파란P 위치/수량

### ❌ 4. 철거 계획 (검정 심볼 + 검정실선)
- 철거케이블: 구간/거리 ("철거 XXm" 텍스트)
- 철거전주: 검정C 위치

### 📝 5. 설계자 주석/메모
- **노란색 하이라이트 텍스트** 전체 기록 (★ 매우 중요)
- 텍스트 박스 내용, 특이사항 메모

### 📷 6. 현장사진
- 도로 환경, 전주 상태, 시설물 상황

### ⚠️ 확인 필요 사항
- 흐려서 읽지 못한 텍스트
- 불명확한 심볼 색상
- ENG시트 데이터와 불일치 부분
"""


def _generate_construction_understanding(
    api_key, parsed_data, image_sources, source_type="snapshot", model="gpt-4o"
):
    """
    행정도에서 파악한 공사 내용을 사용자 검증용으로 요약.
    source_type: "snapshot" | "individual"
    """
    client = get_client(api_key)

    note = ""
    if source_type == "individual":
        note = (
            "\n⚠️ **참고**: 아래 이미지는 행정도에서 추출된 개별 임베디드 이미지입니다.\n"
            "전체 행정도 뷰(선로+심볼+텍스트 합쳐진 복합도면)가 아니므로,\n"
            "선로 심볼이나 텍스트 레이블이 보이지 않을 수 있습니다.\n"
            "보이는 정보만 정확하게 분석해주세요.\n"
        )

    ctx = _build_design_context(parsed_data)

    content_parts = [{"type": "text", "text": (
        f"{CONSTRUCTION_UNDERSTANDING_PROMPT}\n{note}\n"
        f"설계 데이터 (ENG시트 파싱 결과):\n{ctx}\n"
    )}]

    for name, img in image_sources[:8]:
        b64 = encode_image_base64(img.data)
        mime = detect_image_type(img.filename)
        content_parts.append({"type": "text", "text": f"\n--- [{name}] {img.filename} ({len(img.data):,}bytes) ---"})
        content_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}})

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content_parts}],
            max_tokens=3000, temperature=0.1,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"공사 이해 요약 생성 실패: {e}"


# ============================================================
# ★★★ 메인: 통합 AI 검토
# ============================================================
def full_ai_review(
    api_key: str,
    parsed_data: dict,
    rule_results: list,
    sheet_images: dict = None,
    model: str = "gpt-4o",
    snapshots: dict = None,
    user_images: dict = None,
    expert_notes: str = "",
) -> dict:
    """
    통합 AI 검토 실행.

    Args:
        user_images: 사용자가 직접 업로드한 이미지
            {"개황도(전)": bytes, "개황도(후)": bytes, "작업 전 GIS": bytes}

    Returns:
        comprehensive, image_analyses[], comparison,
        construction_understanding, analysis_mode
    """
    result = {
        "comprehensive": "",
        "image_analyses": [],
        "comparison": "",
        "construction_understanding": "",
        "analysis_mode": "text_only",
    }
    snapshots = snapshots or {}
    sheet_images = sheet_images or {}
    user_images = user_images or {}

    # 1. 텍스트 기반 종합 검토 (항상) — 전문가 발췌 노트 포함
    result["comprehensive"] = comprehensive_review(api_key, parsed_data, rule_results, model, expert_notes)

    # ==== 모드 U: 사용자 업로드 이미지 (★ 최우선) ====
    if any(user_images.values()):
        result["analysis_mode"] = "user_upload"
        ui_before = user_images.get("개황도(전)")
        ui_after = user_images.get("개황도(후)")
        ui_gis = user_images.get("작업 전 GIS")
        snaps_for_understanding = []

        # ★★★ 3장 모두 있으면 통합 분석 (GIS + 전 + 후를 한꺼번에)
        if ui_gis and ui_before and ui_after:
            integrated = analyze_integrated_images(
                api_key, ui_gis, ui_before, ui_after, parsed_data, model
            )
            result["image_analyses"].append(
                f"🔬 **통합 분석 (GIS + 개황도 전/후 동시 비교):**\n{integrated}"
            )

        # 개별 이미지 분석 (상세용)
        if ui_gis:
            a = analyze_single_image(api_key, ui_gis, "GIS_사용자업로드.png", parsed_data, model)
            result["image_analyses"].append(f"📤 **작업 전 GIS [사용자 업로드] 분석:**\n{a}")

        if ui_before:
            from models import ImageInfo
            a = analyze_single_image(api_key, ui_before, "개황도(전)_사용자업로드.png", parsed_data, model)
            result["image_analyses"].append(f"📤 **개황도(전) [사용자 업로드] 분석:**\n{a}")
            snaps_for_understanding.append(("개황도(전)", ImageInfo(filename="개황도(전).png", data=ui_before, sheet_name="개황도(전)")))

        if ui_after:
            from models import ImageInfo
            a = analyze_single_image(api_key, ui_after, "개황도(후)_사용자업로드.png", parsed_data, model)
            result["image_analyses"].append(f"📤 **개황도(후) [사용자 업로드] 분석:**\n{a}")
            snaps_for_understanding.append(("개황도(후)", ImageInfo(filename="개황도(후).png", data=ui_after, sheet_name="개황도(후)")))

        # 전/후 비교 분석 (통합 분석이 없을 때 or 추가 상세)
        if ui_before and ui_after and not (ui_gis and ui_before and ui_after):
            result["comparison"] = compare_before_after(
                api_key, ui_before, "전.png", ui_after, "후.png",
                parsed_data, model,
            )

        if snaps_for_understanding:
            result["construction_understanding"] = _generate_construction_understanding(
                api_key, parsed_data, snaps_for_understanding, "user_upload", model
            )
        return result

    # ==== 모드 A: 스냅샷 있음 (최상) ====
    # ★ 개황도/행정도 양쪽 이름 모두 탐색
    snap_before = snapshots.get("행정도(전)") or snapshots.get("개황도(전)")
    snap_after = snapshots.get("행정도(후)") or snapshots.get("개황도(후)")
    snap_gis = snapshots.get("작업 전 GIS")

    if snap_before or snap_after:
        result["analysis_mode"] = "snapshot"
        snaps_for_understanding = []

        if snap_before:
            a = analyze_single_image(api_key, snap_before.data, "개황도(전)_스냅샷.png", parsed_data, model)
            result["image_analyses"].append(f"📑 **개황도(전) 전체 스냅샷 분석:**\n{a}")
            snaps_for_understanding.append(("개황도(전)", snap_before))

        if snap_after:
            a = analyze_single_image(api_key, snap_after.data, "개황도(후)_스냅샷.png", parsed_data, model)
            result["image_analyses"].append(f"📑 **개황도(후) 전체 스냅샷 분석:**\n{a}")
            snaps_for_understanding.append(("개황도(후)", snap_after))

        if snap_gis:
            a = analyze_single_image(api_key, snap_gis.data, "GIS_스냅샷.png", parsed_data, model)
            result["image_analyses"].append(f"📑 **작업 전 GIS 스냅샷 분석:**\n{a}")

        if snap_before and snap_after:
            result["comparison"] = compare_before_after(
                api_key, snap_before.data, "전.png", snap_after.data, "후.png",
                parsed_data, model,
            )

        if snaps_for_understanding:
            result["construction_understanding"] = _generate_construction_understanding(
                api_key, parsed_data, snaps_for_understanding, "snapshot", model
            )
        return result

    # ==== 모드 B: 개별 이미지 (스냅샷 없음) ====
    # ★ 개황도/행정도 양쪽 이름 모두 탐색
    check_names = ["행정도(전)", "행정도(후)", "개황도(전)", "개황도(후)", "작업 전 GIS", "공문 및 사진"]
    has_any = any(sheet_images.get(s) for s in check_names)

    if has_any:
        result["analysis_mode"] = "individual"

        # ★ 중복 제거: 행정도(전)/(후) 동일 이미지면 한 번만
        seen_hashes = set()
        all_unique = []  # (sheet_name, ImageInfo) for construction understanding

        for sname in check_names:
            imgs = sheet_images.get(sname, [])
            if not imgs:
                continue

            unique = []
            for img in imgs:
                h = hashlib.md5(img.data).hexdigest()
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    unique.append(img)
                    all_unique.append((sname, img))

            if not unique:
                result["image_analyses"].append(
                    f"📎 **{sname}**: (개황도(전)과 동일 이미지 — 중복 생략)"
                )
                continue

            # 시트별 배치 분석
            max_n = 6 if ("행정도" in sname or "개황도" in sname) else 4
            a = analyze_images_batch(api_key, unique, sname, parsed_data, model, max_n)
            if a:
                result["image_analyses"].append(f"📎 **{sname}** ({len(unique)}장):\n{a}")

        # ★ 공사 이해 요약 — 개별 이미지에서도 생성
        if all_unique:
            top = sorted(all_unique, key=lambda x: len(x[1].data), reverse=True)[:6]
            result["construction_understanding"] = _generate_construction_understanding(
                api_key, parsed_data, top, "individual", model
            )

    return result
