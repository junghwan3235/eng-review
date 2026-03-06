"""
데이터 모델 정의
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CableInfo:
    """케이블 정보"""
    label: str = ""             # "기설케이블#1" 또는 "다대화#1"
    length_m: int = 0           # 거리(m)
    network_tier: str = ""      # "기간망" | "간선망" | "지선망" | "가입자망"
    cable_type: str = ""        # "Dry" | "MSLT"
    cable_id: str = ""          # 케이블 번호
    total_cores: int = 0        # 전체 코어수
    used_cores: int = 0         # 사용 코어수
    usage_rate: float = 0.0     # 사용률


@dataclass
class EnclosureInfo:
    """함체 정보"""
    label: str = ""             # "기설함체#1" 또는 "신설함체#1"
    pole_id: str = ""           # 한전 전산번호
    sk_name: str = ""           # SK 관리번호
    splice_cores: int = 0       # 접속 코어수


@dataclass
class ReviewIssue:
    """검토 지적사항"""
    code: str = ""              # "R01-1"
    severity: str = ""          # "CRITICAL" | "MAJOR" | "MINOR" | "INFO"
    category: str = ""          # 지적 유형
    message: str = ""           # 지적 내용
    recommendation: str = ""    # 권고사항
    savings_hint: str = ""      # 절감 힌트 (선택)
    reference: str = ""         # 근거 규정 (선택)


@dataclass
class ImageInfo:
    """추출된 이미지 정보"""
    filename: str = ""
    data: bytes = b""
    sheet_name: str = ""        # 출처 시트
    source_sheet: str = ""      # 출처 시트 (alias)
    description: str = ""       # 설명
