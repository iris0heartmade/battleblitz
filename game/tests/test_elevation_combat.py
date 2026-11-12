"""Height rules exercised through both pure mechanics and real HTTP actions."""
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from app.battlefield import Battlefield, bind_battlefield, step_cost, defense_bonus, tile_height
from app.movement import MovementProfile, resolve_movement_profile
from app.game_logic import can_attack_from_position, calculate_damage
from app.models import Tile, Unit
from app.utils import bfs_reachable, pathfind

def tile(x,y=0,terrain="plain",height=0,subtype=None):
    return SimpleNamespace(x=x,y=y,terrain=terrain,elevation=height,subtype=subtype)

def actor(kind="swordsman",x=0,y=0):
    return SimpleNamespace(unit_type=kind,hero_id=None,x=x,y=y,player=None,atk=15,matk=12,
        def_=5,mdef=4,hp=100,morale=0,skills=[],name=kind)

@pytest.mark.parametrize("delta,expected",[(0,2),(1,3),(2,4),(3,5),(4,None),(-1,2),(-3,2),(-4,None)])
def test_ground_step_height_cost(delta,expected):
    field=Battlefield([tile(0),tile(1,height=delta)])
    assert step_cost(MovementProfile({}),field,(0,0),(1,0))==expected

def test_stairs_roads_and_flight():
    field=Battlefield([tile(0),tile(1,terrain="castle",subtype="castle_stairs",height=3)])
    assert step_cost(MovementProfile({}),field,(0,0),(1,0))==2
    field=Battlefield([tile(0),tile(1,terrain="road",height=4)])
    assert step_cost(MovementProfile({}),field,(0,0),(1,0)) is None
    for kind in ["dragon_rider","falcon_knight"]:
        assert step_cost(resolve_movement_profile(actor(kind)),field,(0,0),(1,0))==2

def test_dijkstra_routes_around_cliff():
    field=Battlefield([tile(x,y,height=4 if (x,y)==(1,0) else 0) for y in range(2) for x in range(3)])
    profile=MovementProfile({})
    reachable=bfs_reachable((0,0),field,{},4,viewer_owner_id=None,movement_profile=profile,size=3)
    assert (1,0) not in reachable
    assert reachable[(2,0)]==8
    assert pathfind((0,0),(2,0),field,{},4,viewer_owner_id=None,movement_profile=profile,size=3)==[(0,0),(0,1),(1,1),(2,1),(2,0)]

def test_no_mountain_bonus_or_double_cover():
    assert defense_bonus(tile(0,terrain="mountain",height=None))==0
    assert tile_height(tile(0,terrain="mountain",height=None))==3
    assert defense_bonus(tile(0,terrain="rock"))==0
    assert defense_bonus(tile(0,terrain="forest"))==2
    assert defense_bonus(tile(0,terrain="castle",subtype="castle_throne"))==6

def test_melee_and_high_ranged_target_specific():
    sword=actor()
    bow=actor("archer")
    bow.skills=["snipe"]
    field=Battlefield([tile(0,height=2),tile(1,height=0),tile(6,height=0),tile(5,height=2)])
    bind_battlefield([sword,bow],field)
    assert not can_attack_from_position(sword,0,0,1,0)
    assert can_attack_from_position(bow,0,0,6,0)  # base4 + snipe1 + height1
    assert can_attack_from_position(bow,0,0,5,0)
    assert not can_attack_from_position(bow,0,0,7,0)
    assert not can_attack_from_position(bow,0,0,1,0)  # minimum range unchanged

def test_high_ground_attack_not_cover_passive():
    attacker,target=actor(),actor(x=1)
    field=Battlefield([tile(0,height=3),tile(1)])
    bind_battlefield([attacker,target],field)
    result=calculate_damage(attacker,target,99,crit=False)
    assert result.effective_atk==17
    assert result.defense_total==5
    field.heights[(0,0)]=0
    assert calculate_damage(attacker,target,99,crit=False).effective_atk==15

# Reuse the existing deterministic, fresh HTTP match fixture.
from test_godot_forecast_api import forecast_app, _seed_combat

async def test_http_cliff_rejects_preview_and_execution(forecast_app):
    client, sessions=forecast_app
    game,red,blue,attacker,target=await _seed_combat(sessions)
    async with sessions() as s:
        row=(await s.execute(select(Tile).where(Tile.game_id==game,Tile.x==0))).scalars().first()
        row.elevation=3
        await s.commit()
    args={"player_id":red,"attacker_id":attacker,"target_id":target}
    forecast=await client.get(f"/games/{game}/forecast-attack",params=args)
    actual=await client.post(f"/games/{game}/attack",json=args)
    assert forecast.status_code==actual.status_code==400

async def test_http_half_cost_saved_and_preview_matches(forecast_app):
    client,sessions=forecast_app
    game,red,_,attacker,target=await _seed_combat(sessions)
    async with sessions() as s:
        enemy=await s.get(Unit,target)
        enemy.x,enemy.y=3,0
        cells=(await s.execute(select(Tile).where(Tile.game_id==game))).scalars().all()
        cells[0].elevation=0
        for cell in cells:
            if cell.x==1:
                cell.occupied_unit_id=None
                cell.elevation=1
        s.add(Tile(game_id=game,x=3,y=0,terrain="plain",elevation=0,occupied_unit_id=target))
        await s.commit()
    preview=await client.get(f"/games/{game}/movement-options",params={"player_id":red,"unit_id":attacker})
    assert preview.status_code==200,preview.text
    dest=next(t for t in preview.json()["tiles"] if t["x"]==1)
    assert dest["cost_x2"]==3 and dest["climb_cost_x2"]==1
    moved=await client.post(f"/games/{game}/move",json={"player_id":red,"unit_id":attacker,"to_x":1,"to_y":0})
    assert moved.status_code==200,moved.text
    assert moved.json()["cost"]==1.5
    state=(await client.get(f"/games/{game}/state")).json()
    assert state["elevation_rules"]["version"]==2
    unit=next(u for p in state["players"] for u in p["units"] if u["id"]==attacker)
    assert unit["mp"]==1.5

async def test_http_highground_forecast_execution_and_counter_cover(forecast_app,monkeypatch):
    client,sessions=forecast_app
    game,red,_,attacker,target=await _seed_combat(sessions)
    async with sessions() as s:
        a=await s.get(Unit,attacker); d=await s.get(Unit,target)
        a.hp=a.max_hp=d.hp=d.max_hp=100
        a.skills=[]; d.skills=[]
        d.unit_type="swordsman"
        cells=(await s.execute(select(Tile).where(Tile.game_id==game))).scalars().all()
        for cell in cells:
            cell.elevation=1 if cell.x==0 else 0
            cell.terrain="forest" if cell.x==0 else "rock"
        await s.commit()
    from app.routes import actions
    original=actions.attack_with_double_strike
    import random
    monkeypatch.setattr(actions,"attack_with_double_strike",lambda a,d,b,**kwargs: original(a,d,b,rng=random.Random(0)))
    args={"player_id":red,"attacker_id":attacker,"target_id":target}
    preview=await client.get(f"/games/{game}/forecast-attack",params=args)
    assert preview.status_code==200,preview.text
    assert preview.json()["height_attack_bonus"]==1
    assert preview.json()["target_def_bonus"]==0
    attack=await client.post(f"/games/{game}/attack",json=args)
    assert attack.status_code==200,attack.text
    assert sum(h["damage"] for h in attack.json()["hits"])==preview.json()["damage"]
    assert attack.json()["counter_damage"]==preview.json()["counter_damage"]

