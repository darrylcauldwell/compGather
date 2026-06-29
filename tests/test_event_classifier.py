"""Tests for spectator classification (drives the app's Watch tab)."""

from app.services.event_classifier import classify_spectator


def test_shows_are_spectator():
    assert classify_spectator("Chatsworth Country Fair", "show") is True


def test_international_codes_and_stars_are_spectator():
    assert classify_spectator("Bolesworth International CSI4* Week 1", "competition")
    assert classify_spectator("TSCHIO Aachen", "competition") is False  # 'CHIO' not on a boundary
    assert classify_spectator("CHIO Rotterdam", "competition") is True
    assert classify_spectator("Desert Circuit — CSI3*", "competition") is True
    assert classify_spectator("Keysoe International CSI2* 2026", "competition") is True


def test_marquee_terms_are_spectator():
    assert classify_spectator("Royal Cornwall County Show", "competition")
    assert classify_spectator("FEI World Cup Finals", "competition")
    assert classify_spectator("Nations Cup Hagen", "competition")


def test_grassroots_not_spectator():
    assert classify_spectator("Unaffiliated Dressage", "competition") is False
    assert classify_spectator("Arena Hire Saturday", "competition") is False
    assert classify_spectator("Spring Show Jumping League", "competition") is False
