"""Пакет для проверки методики (пакет L, L6) собирается из кода и не отстаёт от него.

Числа примеров посчитаны движком; файл в репозитории — снимок сборки, и устаревший снимок
роняет этот тест, как устаревшие фикстуры зеркал: правка методики → пересборка пакета.
"""
from __future__ import annotations

from pathlib import Path

from calc_core import run
from calc_core.methodology import methodology_map
from calc_core.methodology_packet import PACKET_PATH, PROPOSALS, build_packet
from calc_core.samples import build_sample_project

ROOT = Path(__file__).resolve().parents[2]


def test_the_packet_in_the_repository_is_fresh():
    assert (ROOT / PACKET_PATH).read_text(encoding="utf-8") == build_packet(), (
        "пакет устарел: пересоберите `python backend/scripts/methodology_packet.py`")


def test_every_point_has_a_proposal_and_nothing_extra():
    """Перечень закрыт в обе стороны: забытый пункт выпал бы из пакета молча, а лишний
    предлагал бы подтвердить то, чего нет."""
    model = build_sample_project()
    ids = {c.id for c in methodology_map(model, run(model)).choices}
    assert set(PROPOSALS) == ids


def test_each_point_carries_its_fingerprint_and_a_place_to_sign():
    text = build_packet()
    model = build_sample_project()
    for choice in methodology_map(model, run(model)).choices:
        assert f"`{choice.fingerprint}`" in text, choice.id
        assert f"## Пункт {choice.number}." in text, choice.id
    assert text.count("Подпись: __________") == len(PROPOSALS)


def test_every_example_shows_a_difference():
    """Пример, где все варианты дают одно и то же, ничего не показывает проверяющему —
    его надо поменять, а не печатать."""
    for choice_id, proposal in PROPOSALS.items():
        example = proposal.example()
        values = {values for _, values in example.rows}
        assert len(values) > 1, choice_id


def test_the_packet_does_not_claim_confirmations_it_does_not_have():
    text = build_packet()
    assert "Подтверждено действующими записями — 0 из 8" in text
    assert "не подтверждён" in text
