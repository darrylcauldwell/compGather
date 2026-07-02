"""Discipline tagging for training/clinic titles (Prepare-pillar data readiness).

The new discipline-word aliases (jumping/jump/gridwork/grid work → Show Jumping,
flatwork/flat work → Dressage) should tag clinic-style names that previously got
no discipline — WITHOUT letting the bare words hijack the specific competition
formats, thanks to EventClassifier's longest-match rule.
"""

from __future__ import annotations

import pytest

from app.services.event_classifier import EventClassifier


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Jumping Clinic with a Coach", "Show Jumping"),
        ("Evening Jump Lesson", "Show Jumping"),
        ("Grid Work Workshop", "Show Jumping"),
        ("Gridwork Clinic", "Show Jumping"),
        ("Flatwork Session", "Dressage"),
        ("Flat Work & Suppleness Clinic", "Dressage"),
        # these already worked — must still work
        ("Dressage Clinic with Steph Cooper", "Dressage"),
        ("XC Schooling", "Cross Country"),
    ],
)
def test_clinic_titles_now_get_a_discipline(name, expected):
    discipline, _ = EventClassifier.classify(name)
    assert discipline == expected


@pytest.mark.parametrize(
    "name, expected",
    [
        # longest-match must keep specific formats winning over bare jumping/jump
        ("Jumping With Style Qualifier", "Jumping With Style"),
        ("NSEA Arena Eventing", "Arena Eventing"),
        ("Spring Show Jumping Championship", "Show Jumping"),
    ],
)
def test_specific_formats_not_hijacked(name, expected):
    discipline, _ = EventClassifier.classify(name)
    assert discipline == expected


def test_event_type_unaffected_by_new_aliases():
    # A clinic is still typed training; the discipline aliases only add a discipline.
    discipline, event_type = EventClassifier.classify("Jumping Clinic with a Coach")
    assert event_type == "training"
    assert discipline == "Show Jumping"


@pytest.mark.parametrize(
    "name",
    [
        "Area 6 B+ Test",
        "Wyre Forest PC Mounted Games Practice",
        "Working Rallies",
        "Nithsdale Pony Club Efficiency Tests for D, D+ and C test",
        "Area 2 Senior Members Study Day",
        "Tack Achievement Badge Afternoon",
        "C+ Care Test Only",
        "Area 5 Range Conducting Officer Course",
    ],
)
def test_pony_club_training_terms_classified_training(name):
    # PC efficiency tests / rallies / practice / badges are training, not competition.
    _, event_type = EventClassifier.classify(name)
    assert event_type == "training"


@pytest.mark.parametrize(
    "name",
    [
        "Area Showjumping Qualifier",
        "Spring Dressage Championship",
        "Winter Triathlon Finals 2026",
    ],
)
def test_genuine_pc_competitions_stay_competition(name):
    # PC-training keywords must not drag real competitions out of the Compete feed.
    _, event_type = EventClassifier.classify(name)
    assert event_type == "competition"
