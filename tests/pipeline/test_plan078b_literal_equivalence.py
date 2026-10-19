"""PLAN-078b b9 / D2: dose and frequency checks accept equivalent writings but still catch real defects.

Before this change 12 of 15 correct-but-differently-written translations (毫克, 全角％, 每2周,
每日两次 ...) were flagged, which is why the checks could not be promoted to blockers. Each
defect case below is something the check must keep catching.
"""
from __future__ import annotations

import pytest

from qyunslation.pipeline.qa.pdf_inspect import check_protected_literals

CORRECT = [
    ("同单位，无空格", "Patients received 300 mg every two weeks.", "患者每两周接受300mg。"),
    ("同单位，有空格", "Patients received 300 mg every two weeks.", "患者每两周接受 300 mg。"),
    ("毫克", "Patients received 300 mg every two weeks.", "患者每两周接受 300 毫克。"),
    ("毫克，无空格", "Patients received 300 mg every two weeks.", "患者每两周接受300毫克。"),
    ("毫克/千克", "Dose was 5 mg/kg.", "剂量为 5 毫克/千克。"),
    ("毫克/公斤", "Dose was 5 mg/kg.", "剂量为 5 毫克/公斤。"),
    ("毫升", "A volume of 2 mL was given.", "给药体积为 2 毫升。"),
    ("微克", "Use 50 mcg daily.", "每日使用 50 微克。"),
    ("全角百分号", "Response was 45% at week 16.", "第16周应答率为45％。"),
    ("每2周", "300 mg Q2W.", "300 mg，每2周一次。"),
    ("每两周", "300 mg Q2W.", "300 mg，每两周一次。"),
    ("每隔2周", "300 mg Q2W.", "300 mg，每隔2周给药。"),
    ("每日两次", "Take 10 mg BID.", "每日两次，每次 10 mg。"),
    ("每日一次", "Take 10 mg QD.", "每日一次，每次 10 mg。"),
    ("每日三次", "Take 10 mg TID.", "每日三次，每次 10 mg。"),
    ("保留英文缩写", "300 mg Q2W.", "300 mg Q2W。"),
]

DEFECTS = [
    ("剂量数值改变", "Patients received 300 mg every two weeks.", "患者每两周接受 200 毫克。", "LITERAL_MISSING_DOSE"),
    ("剂量被漏掉", "Patients received 300 mg every two weeks.", "患者每两周接受治疗。", "LITERAL_MISSING_DOSE"),
    ("单位改变 mg->g", "Dose was 5 mg.", "剂量为 5 克。", "LITERAL_MISSING_DOSE"),
    ("单位改变 mg->mL", "Dose was 5 mg.", "剂量为 5 毫升。", "LITERAL_MISSING_DOSE"),
    ("数字只是更大数字的一部分", "Dose was 5 mg.", "剂量为 15 毫克。", "LITERAL_MISSING_DOSE"),
    ("频次改成每4周", "300 mg Q2W.", "300 mg，每4周一次。", "LITERAL_MISSING_FREQ"),
    ("每12周不是每2周", "300 mg Q2W.", "300 mg，每12周一次。", "LITERAL_MISSING_FREQ"),
    ("频次被漏掉", "300 mg Q2W.", "300 mg。", "LITERAL_MISSING_FREQ"),
    ("BID 改成 QD", "Take 10 mg BID.", "每日一次，每次 10 mg。", "LITERAL_MISSING_FREQ"),
    ("TID 改成 BID", "Take 10 mg TID.", "每日两次，每次 10 mg。", "LITERAL_MISSING_FREQ"),
]


@pytest.mark.parametrize("label,source,target", CORRECT, ids=[c[0] for c in CORRECT])
def test_equivalent_writing_is_not_flagged(label, source, target):
    assert check_protected_literals(source, target) == []


@pytest.mark.parametrize("label,source,target,code", DEFECTS, ids=[d[0] for d in DEFECTS])
def test_real_defects_are_still_caught(label, source, target, code):
    assert code in {f.code for f in check_protected_literals(source, target)}


def test_spelled_out_percentages_remain_a_known_limit():
    """"百分之四十五" is not recognised as 45%: it stays flagged (a warning) rather than guessed at."""
    codes = {f.code for f in check_protected_literals("Response was 45%.", "应答率为百分之四十五。")}
    assert codes == {"LITERAL_MISSING_DOSE"}


def test_other_literal_kinds_are_unchanged():
    codes = {f.code for f in check_protected_literals("Write to a@b.org (NCT01234567).", "请联系我们。")}
    assert {"LITERAL_MISSING_EMAIL", "LITERAL_MISSING_IND"} <= codes
