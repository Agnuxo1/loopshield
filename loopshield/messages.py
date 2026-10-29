"""Patient messages for each pathway and step, in English and Arabic.

Deterministic templates are the safe default: they need no language model and contain no
personal data. A model can personalise them only through the privacy gateway.
Every template must be reviewed clinically before use; the Arabic text is a prototype
translation pending review by native speakers and clinicians.
Replies are handled by the engine (`patient_reply`): 1 = understood, 2 = call me, 3 = other language.
Emergency number: 998 (ambulance, United Arab Emirates).
"""
from __future__ import annotations

OWNER = {
    "en": {"screening_programme": "the screening programme", "primary_care": "your family doctor",
           "gastroenterology": "the gastroenterology clinic", "breast_imaging": "the breast imaging clinic",
           "navigator": "a care navigator", "clinical_lead": "the clinical lead"},
    "ar": {"screening_programme": "برنامج الكشف المبكر", "primary_care": "طبيب الأسرة",
           "gastroenterology": "عيادة الجهاز الهضمي", "breast_imaging": "عيادة تصوير الثدي",
           "navigator": "منسق الرعاية", "clinical_lead": "الطبيب المسؤول"},
}

# Per pathway: test name, follow-up test, opening text.
PATHWAY_TEXT = {
    "crc-fit-positive": {
        "en": {"test": "a colonoscopy",
               "first": ("Your bowel screening test (FIT) found a small amount of blood in the sample. "
                         "This is a screening result, not a diagnosis: most people with this result do not have "
                         "cancer, but a colonoscopy is needed to find the cause.")},
        "ar": {"test": "تنظير القولون",
               "first": ("أظهر فحص الكشف المبكر للأمعاء (فحص الدم الخفي في البراز) وجود كمية صغيرة من الدم في العينة. "
                         "هذه نتيجة فحص كشف مبكر وليست تشخيصاً: معظم من تظهر لديهم هذه النتيجة لا يعانون من السرطان، "
                         "لكن تنظير القولون ضروري لمعرفة السبب.")},
    },
    "breast-birads0": {
        "en": {"test": "more breast imaging",
               "first": ("Your screening mammogram needs more pictures to be complete. "
                         "This is a screening result, not a diagnosis: most people who are called back do not have "
                         "cancer, but the extra imaging is needed to check the area.")},
        "ar": {"test": "صور إضافية للثدي",
               "first": ("يحتاج تصوير الثدي الإشعاعي للكشف المبكر إلى صور إضافية لاستكماله. "
                         "هذه نتيجة فحص كشف مبكر وليست تشخيصاً: معظم من يُطلب منهم العودة لا يعانون من السرطان، "
                         "لكن التصوير الإضافي ضروري لفحص المنطقة.")},
    },
}

NEXT = {
    "en": {"NOTIFIED": "your care team will contact you within a few days to explain the result",
           "ACKNOWLEDGED": "please reply to confirm you have read this message",
           "REFERRED": "you will be referred for {test}",
           "REFERRAL_ACCEPTED": "the clinic will confirm your referral",
           "BOOKED": "the clinic will call you to agree an appointment date",
           "ATTENDED": "go to your appointment and follow the clinic's instructions",
           "RESULTED": "the clinic will share your result",
           "CLOSED": "your care team will tell you the next step"},
    "ar": {"NOTIFIED": "سيتواصل معك فريق الرعاية خلال أيام قليلة لشرح النتيجة",
           "ACKNOWLEDGED": "يرجى الرد لتأكيد أنك قرأت هذه الرسالة",
           "REFERRED": "سيتم تحويلك لإجراء {test}",
           "REFERRAL_ACCEPTED": "ستؤكد العيادة استلام التحويل",
           "BOOKED": "ستتصل بك العيادة للاتفاق على موعد",
           "ATTENDED": "احضر موعدك واتبع تعليمات العيادة",
           "RESULTED": "ستبلغك العيادة بالنتيجة",
           "CLOSED": "سيخبرك فريق الرعاية بالخطوة التالية"},
}

FIRST_TAIL = {"en": " Next step: {next}. Responsible team: {owner}.",
              "ar": " الخطوة التالية: {next}. الفريق المسؤول: {owner}."}

OVERDUE = {
    "en": ("We have not yet seen the next step of your follow-up ({next}). "
           "If something makes it difficult (time, transport, worry, cost), reply 2 to ask {navigator} to call you."),
    "ar": ("لم نسجل بعد الخطوة التالية من متابعتك ({next}). "
           "إذا كان هناك ما يصعّب ذلك (الوقت أو المواصلات أو القلق أو التكلفة)، أرسل 2 لتطلب أن يتصل بك {navigator}."),
}

REPLY = {
    "en": "Reply 1 if you understood, 2 to ask for a call from the care team, 3 for another language.",
    "ar": "أرسل 1 إذا فهمت الرسالة، أو 2 لتطلب اتصالاً من فريق الرعاية، أو 3 للتواصل بلغة أخرى.",
}

URGENT = {
    "en": "Please call your clinic today. If you feel very unwell, call an ambulance (998).",
    "ar": "يرجى الاتصال بعيادتك اليوم. إذا شعرت بتوعك شديد، اتصل بالإسعاف (998).",
}


def patient_message(case, kind: str = "first") -> str:
    lang = case.language if case.language in REPLY else "en"
    texts = PATHWAY_TEXT[case.pathway.code][lang]
    step = case.pending_step
    nxt = NEXT[lang].get(step.state, "").format(test=texts["test"]) if step else ""
    if kind == "first":
        text = texts["first"] + FIRST_TAIL[lang].format(next=nxt, owner=OWNER[lang].get(case.owner_role,
                                                                                       case.owner_role))
    elif kind == "overdue":
        text = OVERDUE[lang].format(next=nxt, navigator=OWNER[lang]["navigator"])
    else:
        raise ValueError(kind)
    parts = [text, REPLY[lang]]
    if case.urgent:
        parts.append(URGENT[lang])
    return " ".join(parts)
