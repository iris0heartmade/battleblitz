# Youko bard hero

## Goal

Add a new named hero, Youko (`youko` / 洋子), as a T1 special bard class. Bards are hero-only for now and must not appear in the ordinary recruit roster.

## Design Tree

- Hero content
  - `youko`
    - display name: 洋子
    - base class: `bard`
    - active skill: `sing`
    - assets: grid sprite, portrait, crest
- Unit class
  - `bard`
    - T1 support profile
    - default skill: `sing`
    - absent from `RECRUIT_COST`
- Skill
  - `sing`
    - targets adjacent allied unit
    - target must have already acted or moved
    - refreshes target action flags and MP
    - consumes Youko's action
- Verification
  - registry tests
  - skill behavior tests
  - recruit roster exception for special class
  - asset presence check
