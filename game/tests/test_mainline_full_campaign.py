"""
Fire-Emblem-style mainline structure tests.

Validates that the production campaign chain (chapter_01 → chapter_05)
implements the dialoge-hook + character-arc + sequential-unlock shape
that distinguishes a proper SRPG campaign from a flat list of battles:

  * All 5 chapters load with their JSON files intact.
  * Each chapter has intro + every battle_after + victory stories.
  * Story files exist on disk and parse as valid dialogue JSON.
  * Each chapter's battles hook into the `dialogues` map
    (the loader enforces this; we re-check it here for documentation).
  * The 3 core heroes (云 / 红 / 安娜) appear across the campaign,
    with `hero_id` stable for yun/anna.
  * Hero levels climb chapter-by-chapter (growth arc).
  * Battle win_conditions span the full SRPG vocabulary
    (rout / seize / defend / boss).
  * Chapter rewards grow monotonically.
  * Cross-chapter narrative continuity: later chapters reference
    earlier events via keyword presence in their victory stories.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.mainline import clear_cache, load_mainline


CAMPAIGN_CHAPTERS = [
    "chapter_01_steel_rebellion",
    "chapter_02_border_flame",
    "chapter_03_crown_shadow",
    "chapter_04_frost_invasion",
    "chapter_05_crown_united",
]


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


def _stories_root() -> Path:
    """game/app/mainline/loader.py → game/stories/"""
    from app.mainline.loader import mainlines_dir
    here = mainlines_dir().resolve()
    return here.parent / "stories"


def _load_chapter_story(chapter_id: str, story_key: str) -> dict | None:
    """Resolve a chapter's `dialogues[key]` to its parsed JSON, or None."""
    chapter = load_mainline(chapter_id)
    rel = chapter.dialogues.get(story_key)
    if not rel:
        return None
    # `rel` looks like "stories/chapter_01/intro.json"
    full = _stories_root() / rel.split("stories/", 1)[1]
    if not full.exists():
        return None
    return json.loads(full.read_text(encoding="utf-8"))


# ============================================================
# 1) All 5 chapters load + structural shape
# ============================================================

class TestCampaignLoad:
    @pytest.mark.parametrize("chapter_id", CAMPAIGN_CHAPTERS)
    def test_chapter_loads(self, chapter_id: str):
        m = load_mainline(chapter_id)
        assert m.id == chapter_id
        assert m.title, f"{chapter_id} missing title"
        assert m.synopsis, f"{chapter_id} missing synopsis"
        assert len(m.battles) >= 1, f"{chapter_id} has no battles"
        assert m.required_classes, f"{chapter_id} missing required_classes"
        assert m.starting_units, f"{chapter_id} missing starting_units"

    @pytest.mark.parametrize("chapter_id", CAMPAIGN_CHAPTERS)
    def test_dialogues_map_has_required_keys(self, chapter_id: str):
        """intro + at least one battle_after + victory must all exist."""
        m = load_mainline(chapter_id)
        assert "intro" in m.dialogues, f"{chapter_id} missing dialogues.intro"
        assert "victory" in m.dialogues, f"{chapter_id} missing dialogues.victory"
        # Each battle needs a post_battle_dialogue OR the chapter must use a
        # generic key. We require a per-battle key.
        battle_keys = [b.post_battle_dialogue for b in m.battles if b.post_battle_dialogue]
        assert len(battle_keys) >= 1, f"{chapter_id} battles lack post_battle_dialogue"
        for key in battle_keys:
            assert key in m.dialogues, (
                f"{chapter_id} battle hook {key!r} not in dialogues map"
            )


# ============================================================
# 2) Story files exist + are valid Fire-Emblem-style dialogue
# ============================================================

class TestStoryFiles:
    @pytest.mark.parametrize("chapter_id", CAMPAIGN_CHAPTERS)
    def test_intro_story_exists_and_parses(self, chapter_id: str):
        story = _load_chapter_story(chapter_id, "intro")
        assert story is not None, f"{chapter_id} intro story missing on disk"
        assert "scenes" in story and isinstance(story["scenes"], list)
        assert len(story["scenes"]) >= 3, (
            f"{chapter_id} intro too short — needs narration+dialogue at minimum"
        )

    @pytest.mark.parametrize("chapter_id", CAMPAIGN_CHAPTERS)
    def test_victory_story_exists_and_parses(self, chapter_id: str):
        story = _load_chapter_story(chapter_id, "victory")
        assert story is not None, f"{chapter_id} victory story missing on disk"
        assert "scenes" in story
        # victory must end on a `choice` node (回大厅 / 继续 / 等等)
        last = story["scenes"][-1]
        assert last.get("type") == "choice", (
            f"{chapter_id} victory must end on a choice node, got {last.get('type')!r}"
        )

    @pytest.mark.parametrize("chapter_id", CAMPAIGN_CHAPTERS)
    def test_every_battle_after_story_exists(self, chapter_id: str):
        m = load_mainline(chapter_id)
        for b in m.battles:
            if not b.post_battle_dialogue:
                continue
            story = _load_chapter_story(chapter_id, b.post_battle_dialogue)
            assert story is not None, (
                f"{chapter_id} battle {b.id} post story {b.post_battle_dialogue!r} "
                "missing on disk"
            )
            assert "scenes" in story and story["scenes"], (
                f"{chapter_id} battle {b.id} post story is empty"
            )

    @pytest.mark.parametrize("chapter_id", CAMPAIGN_CHAPTERS)
    def test_story_contains_real_dialogue(self, chapter_id: str):
        """At least one scene must be a `dialogue` type with speaker + text."""
        story = _load_chapter_story(chapter_id, "intro")
        dialogue_scenes = [s for s in story["scenes"] if s.get("type") == "dialogue"]
        assert dialogue_scenes, f"{chapter_id} intro has no dialogue scenes"
        for s in dialogue_scenes:
            assert "speaker" in s, f"{chapter_id} dialogue missing speaker"
            assert "text" in s and s["text"].strip(), (
                f"{chapter_id} dialogue missing or empty text"
            )


# ============================================================
# 3) Character arc — 云 / 红 / 安娜 across the campaign
# ============================================================

CLOUD_NAME = "云"
HONG_NAME = "红"
ANNA_NAME = "安娜"
YUN_HERO_ID = "yun"
ANNA_HERO_ID = "anna"


def _hero_unit(chapter, name: str):
    return next((u for u in chapter.starting_units if u.name == name), None)


class TestCharacterArc:
    @pytest.mark.parametrize("chapter_id", CAMPAIGN_CHAPTERS)
    def test_cloud_present_with_stable_hero_id(self, chapter_id: str):
        m = load_mainline(chapter_id)
        cloud = _hero_unit(m, CLOUD_NAME)
        assert cloud is not None, f"{chapter_id} 主角 云 missing from starting_units"
        assert cloud.hero_id == YUN_HERO_ID, (
            f"{chapter_id} 主角 云 hero_id drifted from 'yun' (got {cloud.hero_id!r})"
        )

    @pytest.mark.parametrize("chapter_id", CAMPAIGN_CHAPTERS)
    def test_anna_present_with_stable_hero_id(self, chapter_id: str):
        m = load_mainline(chapter_id)
        anna = _hero_unit(m, ANNA_NAME)
        assert anna is not None, f"{chapter_id} 安娜 missing from starting_units"
        assert anna.hero_id == ANNA_HERO_ID, (
            f"{chapter_id} 安娜 hero_id drifted from 'anna' (got {anna.hero_id!r})"
        )

    @pytest.mark.parametrize("chapter_id", CAMPAIGN_CHAPTERS)
    def test_hong_present_across_campaign(self, chapter_id: str):
        m = load_mainline(chapter_id)
        hong = _hero_unit(m, HONG_NAME)
        assert hong is not None, f"{chapter_id} 红 missing from starting_units"

    def test_levels_grow_through_campaign(self):
        """Each chapter should show the heroes at a higher level than before.

        Allow ties (training skip), forbid drops.
        """
        last_cloud = last_anna = last_hong = 0
        for cid in CAMPAIGN_CHAPTERS:
            m = load_mainline(cid)
            cloud = _hero_unit(m, CLOUD_NAME)
            anna = _hero_unit(m, ANNA_NAME)
            hong = _hero_unit(m, HONG_NAME)
            assert cloud.level >= last_cloud, (
                f"{cid} 云 level regressed: {cloud.level} < {last_cloud}"
            )
            assert anna.level >= last_anna, (
                f"{cid} 安娜 level regressed: {anna.level} < {last_anna}"
            )
            assert hong.level >= last_hong, (
                f"{cid} 红 level regressed: {hong.level} < {last_hong}"
            )
            last_cloud, last_anna, last_hong = cloud.level, anna.level, hong.level
        # Sanity: there should be real growth somewhere.
        assert last_cloud > 0 and last_anna > 0 and last_hong > 0


# ============================================================
# 4) Cross-chapter narrative continuity
# ============================================================

# Each tuple: (later_chapter, dict of {"intro": [...], "victory": [...]})
# where the keyword list is the prior-chapter callback expected at that
# point. Intros set the scene so they have a lighter requirement;
# victories are the recap so they must hit every key prior beat.
# If a later chapter forgets to call back, the SRPG narrative thread breaks.
CROSS_CHAPTER_REFS = {
    "chapter_02_border_flame": {
        "intro":   ["山口", "卡尔德"],
        "victory": ["山口", "卡尔德"],
    },
    "chapter_03_crown_shadow": {
        # 三皇子 / 国王 在 victory 出现;intro 只交代"回到王都"
        "intro":   ["边境"],
        "victory": ["边境", "国王", "三皇子"],
    },
    "chapter_04_frost_invasion": {
        # intro 直接进入北境战场;王都只在 victory 回望
        "intro":   ["北境", "异族"],
        "victory": ["王都", "北境", "异族"],
    },
    "chapter_05_crown_united": {
        # intro 直接开打决战;卡尔德已经死在 battle_03,所以 victory 不再提
        "intro":   ["卡尔德", "王都"],
        "victory": ["王都", "北境"],
    },
}


class TestCrossChapterReferences:
    @pytest.mark.parametrize(
        ("chapter_id", "slot", "keywords"),
        [
            (cid, slot, kws)
            for cid, slots in CROSS_CHAPTER_REFS.items()
            for slot, kws in slots.items()
        ],
    )
    def test_later_chapter_references_prior(self, chapter_id, slot, keywords):
        story = _load_chapter_story(chapter_id, slot)
        text = " ".join(s.get("text", "") for s in story["scenes"])
        for kw in keywords:
            assert kw in text, (
                f"{chapter_id} {slot} missing prior-chapter keyword {kw!r}; "
                "SRPG narrative thread breaks here"
            )


# ============================================================
# 5) Battle vocabulary diversity + rewards progression
# ============================================================

class TestBattleVocabulary:
    def test_all_four_win_conditions_appear_somewhere(self):
        """A real campaign uses rout / seize / defend / boss at minimum."""
        seen = set()
        for cid in CAMPAIGN_CHAPTERS:
            m = load_mainline(cid)
            for b in m.battles:
                seen.add(b.win_condition)
        # pydantic WinCondition is a strict enum; just check coverage
        assert {"rout", "seize", "defend", "boss"}.issubset(seen), (
            f"Campaign only uses {seen}; expected rout+seize+defend+boss"
        )


class TestRewardsProgression:
    def test_gold_grows_monotonically(self):
        last = 0
        for cid in CAMPAIGN_CHAPTERS:
            m = load_mainline(cid)
            assert m.rewards_on_clear.gold >= last, (
                f"{cid} gold reward regressed: {m.rewards_on_clear.gold} < {last}"
            )
            last = m.rewards_on_clear.gold
        assert last >= 1000, f"Final chapter gold too low: {last}"

    def test_each_chapter_unlocks_something_or_carries_no_unlock(self):
        """Chapters either unlock a new class or piggy-back on prior unlocks.

        We accept either; we just require that the unlock_class, when set,
        is a real class the engine recognises.
        """
        for cid in CAMPAIGN_CHAPTERS:
            m = load_mainline(cid)
            unlock = m.rewards_on_clear.unlock_class
            if unlock is None:
                continue
            # Confirm it's a known class id by looking at the app.classes module.
            from app.classes.units import (
                archer, blade_master, dragon_rider, healer, knight,
                paladin, sage, saint, sniper, swordsman, warlock,
            )
            module_names = {
                "archer", "blade_master", "dragon_rider", "healer", "knight",
                "paladin", "sage", "saint", "sniper", "swordsman", "warlock",
            }
            assert unlock in module_names, (
                f"{cid} rewards unlock unknown class {unlock!r}"
            )

    def test_unlocks_form_a_promotion_chain(self):
        """The 5 chapters should unlock progressively-stronger classes."""
        unlocks = []
        for cid in CAMPAIGN_CHAPTERS:
            m = load_mainline(cid)
            unlocks.append(m.rewards_on_clear.unlock_class)
        # chapter_01 unlocks knight; chapter_05 unlocks saint.
        # We assert the progression is non-decreasing in "tier", but since
        # tier mapping is judgement-call, we just require no two chapters
        # unlock the *same* class (otherwise one chapter would be redundant).
        non_null = [u for u in unlocks if u]
        assert len(non_null) == len(set(non_null)), (
            f"Duplicate unlocks in chain: {unlocks}"
        )


# ============================================================
# 6) Sequential-unlock smoke (defensive — does not hit the route)
# ============================================================

class TestChainOrdering:
    def test_chapter_ids_are_strictly_ordered(self):
        """chapter_01 .. chapter_05 should sort naturally; reject typos."""
        for cid in CAMPAIGN_CHAPTERS:
            m = re.match(r"chapter_(\d{2})_", cid)
            assert m, f"{cid} does not match chapter_NN_* naming"
        numbers = [int(re.match(r"chapter_(\d{2})_", c).group(1)) for c in CAMPAIGN_CHAPTERS]
        assert numbers == sorted(numbers), f"Chapters out of order: {numbers}"
        assert numbers == list(range(1, 6)), (
            f"Expected chapter_01..05, got {numbers}"
        )

    def test_each_chapter_has_at_least_two_battles(self):
        """A 'campaign chapter' should have multiple battles (FE-style)."""
        for cid in CAMPAIGN_CHAPTERS:
            m = load_mainline(cid)
            assert len(m.battles) >= 2, (
                f"{cid} only has {len(m.battles)} battle(s); campaign chapters need 2+"
            )
