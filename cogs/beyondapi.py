from math import ceil
from collections import OrderedDict, defaultdict
from itertools import chain
import re
from pprint import pprint

import requests

URL_BASE = "https://www.dndbeyond.com"
CHARACTER_URL = URL_BASE + "/character/{id}/json"
CONFIG_URL = URL_BASE + "/api/config/json"

ROLL_EXPR = re.compile(r'\s*(.+?)\s*:\s*(.+)')


def slug(text):
    return text.lower().replace(' ', '-')


class Character:
    def __init__(self, id):
        self.setup()
        self.url = CHARACTER_URL.format(id=id)
        r = requests.get(self.url)
        if not r:
            raise ValueError('Could not find character\nYou may need to share it publicly')
        self.json = r.json()

    def setup(self):
        r = requests.get(CONFIG_URL)
        if not r:
            raise ValueError('Could not access D&D Beyond')
        config = r.json()

        self.stat_list = []
        for stat in config['stats']:
            name = slug(stat['name'])
            self.stat_list.append(name)
        self.skill_list = {}
        self.skill_ids = {}
        for skill in config['abilitySkills']:
            name = slug(skill['name'])
            self.skill_list[name] = skill['stat']
            self.skill_ids[skill['id']] = name

        self.adjustment_types = {d['id']: d for d in config['adjustmentTypes']}
        self.damage_types = {d['id']: slug(d['name']) for d in config['damageTypes']}

        self.weapon_properties = {}
        for prop in config['weaponProperties']:
            name = slug(prop['name'])
            self.weapon_properties[name] = prop['id']
        self.weapon_categories = {}
        self.weapons = {}
        for c in config['weaponCategories']:
            name = slug(c['name'])
            self.weapon_categories[c['id']] = name
            self.weapons[name] = []
        for weapon in config['weapons']:
            self.weapons[self.weapon_categories[weapon['categoryId']]].append(slug(weapon['name']))

    @property
    def adjustments(self):
        if not hasattr(self, '_adjustments'):
            adjustments = defaultdict(dict)
            for value in self.json['characterValues']:
                type = self.adjustment_types[value['typeId']]
                adjustments[type['name']][value['valueId']] = value
            self._adjustments = dict(adjustments)
        return self._adjustments

    @property
    def name(self):
        return self.json['name']

    def get_value(self, stat, base=0):
        """Calculates the final value of a stat, based on modifiers and feats..."""
        setval = None
        for modtype in self.json['modifiers'].values():
            for mod in modtype:
                if not mod['subType'] == stat:
                    pass
                elif mod['type'] == 'bonus':
                    base += mod['value'] or self.get_mod(mod['statId'])
                elif mod['type'] == 'set':
                    temp = mod['value'] or self.get_mod(mod['statId'])
                    if setval is None or temp > setval:
                        setval = temp

        if setval is not None:
            return max(base, setval)
        return base

    @property
    def classes(self):
        if not hasattr(self, '_classes'):
            self._classes = {c['id']: c for c in self.json['classes']}
        return self._classes

    @property
    def stats(self):
        if hasattr(self, '_stats'):
            return self._stats

        stats = {}

        base = {s['id']: s['value'] for s in self.json['stats']}
        bonus = {s['id']: s['value'] for s in self.json['bonusStats']}
        override = {s['id']: s['value'] for s in self.json['overrideStats']}

        for i, stat in enumerate(self.stat_list):
            name = stat[:3]
            if override[i + 1] is not None:
                s = override[i + 1]
            else:
                s = 10
                s = base[i + 1] or s
                s += bonus[i + 1] or 0
                s = self.get_value(f"{stat}-score", base=s)
            stats[name] = s
            stats[name + 'mod'] = s // 2 - 5

        prof = int(ceil(self.levels['character'] / 4)) + 1
        stats['prof'] = self.get_value('proficiency-bonus', base=prof)

        self._stats = stats
        return stats

    def get_mod(self, name):
        if isinstance(name, int):
            name = self.stat_list[name - 1]
        return self.stats[name[:3] + 'mod']

    @property
    def levels(self):
        if not hasattr(self, '_levels'):
            levels = {}
            for c in self.json['classes']:
                levels[c['definition']['name'].lower()] = c['level']
            levels['character'] = sum(levels.values())
            self._levels = levels
        return self._levels

    @property
    def ac(self):
        if hasattr(self, '_ac'):
            return self._ac

        ac = 10
        armortype = None

        for item in self.json['inventory']:
            if item['equipped'] and item['definition']['filterType'] == 'Armor':
                ac = item['definition']['armorClass']
                armortype = item['definition']['type']

        ac = self.get_value('armor-class', base=ac)

        if armortype is None:
            ac += self.stats['dexmod'] + self.get_value('unarmored-armor-class')
        elif armortype == 'Light Armor':
            ac += self.stats['dexmod']
        elif armortype == 'Medium Armor':
            ac += min(self.stats['dexmod'], 2)

        self._ac = ac
        return ac

    @property
    def skills(self):
        if hasattr(self, '_skills'):
            return self._skills

        proficiency = self.stats['prof']

        skills = OrderedDict()
        profs = {}
        bonuses = {}
        overrides = {}

        # get modifiers
        for modtype in self.json['modifiers'].values():
            for mod in modtype:
                name = mod['subType']
                if mod['type'] == 'half-proficiency':
                    profs[name] = max(profs.get(name, 0), 2)
                elif mod['type'] == 'proficiency':
                    profs[name] = max(profs.get(name, 0), 3)
                elif mod['type'] == 'expertise':
                    profs[name] = 4
                elif mod['type'] == 'bonus':
                    if mod['isGranted']:
                        bonuses[name] = bonuses.get(name, 0) + mod['value']

        for i, skill in enumerate(self.skill_list.keys()):
            skills[skill] = self.get_mod(self.skill_list[skill])
        for i, stat in enumerate(self.stat_list):
            skills[stat + '-saving-throws'] = self.get_mod(stat)

        # handle custom skills
        for s in self.json['customProficiencies']:
            if s['type'] == 1:
                name = slug(s['name'])
                skills[name] = self.get_mod(s['statId'])
                profs[name] = s['proficiencyLevel']
                bonuses[name] = bonuses.get(name, 0) + (s['magicBonus'] or 0) + (s['miscBonus'] or 0)
                if s['override'] is not None:
                    overrides[name] = s['override']

        skills['initiative'] = self.get_mod(2)

        # adjustments
        skill_bonuses = self.adjustments.get('Skill Magic Bonus', {}).values()
        skill_bonuses = chain(skill_bonuses, self.adjustments.get('Skill Misc Bonus', {}).values())
        for adj in skill_bonuses:
            skill = self.skill_ids[adj['valueId']]
            bonuses[skill] = bonuses.get(skill, 0) + (adj['value'] or 0)
        for adj in self.adjustments.get('Skill Override', {}).values():
            skill = self.skill_ids[adj['valueId']]
            if adj['value'] is not None:
                overrides[skill] = adj['value']
        for adj in self.adjustments.get('Skill Proficiency Level', {}).values():
            skill = self.skill_ids[adj['valueId']]
            if adj['value'] is not None:
                profs[skill] = adj['value']
        for adj in self.adjustments.get('Skill Stat Override', {}).values():
            skill = self.skill_ids[adj['valueId']]
            if adj['value'] is not None:
                skills[skill] = self.get_mod(adj['value'])
        save_bonuses = self.adjustments.get('Saving Throw Magic Bonus', {}).values()
        save_bonuses = chain(skill_bonuses, self.adjustments.get('Saving Throw Misc Bonus', {}).values())
        for adj in save_bonuses:
            skill = self.stat_list[adj['valueId'] - 1] + '-saving-throws'
            bonuses[skill] = bonuses.get(skill, 0) + (adj['value'] or 0)
        for adj in self.adjustments.get('Saving Throw Override', {}).values():
            skill = self.stat_list[adj['valueId'] - 1] + '-saving-throws'
            if adj['value'] is not None:
                overrides[skill] = adj['value']
        for adj in self.adjustments.get('Saving Throw Proficiency Level', {}).values():
            skill = self.stat_list[adj['valueId'] - 1] + '-saving-throws'
            if adj['value'] is not None:
                profs[skill] = adj['value']

        # proficiency and bonuses
        for name in skills:
            type = None
            if name.endswith('-saving-throws'):
                type = 'saving-throws'
            elif name in self.skill_list and name != 'initiative':
                type = 'ability-checks'
            prof = max(profs.get(name, 1), profs.get(type, 1))
            bonus = bonuses.get(name, 0) + bonuses.get(type, 0)
            if prof == 2:  # half proficiency
                skills[name] += proficiency // 2
            elif prof == 3:  # proficiency
                skills[name] += proficiency
            elif prof == 4:  # expertise
                skills[name] += proficiency * 2
            skills[name] += bonus

        for name, value in overrides.items():
            skills[name] = value

        for stat in self.stat_list:
            skills[stat[:3] + 'save'] = skills.pop(stat + '-saving-throws')

        self._skills = skills
        return skills

    @property
    def fighting_styles(self):
        if not hasattr(self, '_fighting_styles'):
            fighting_styles = set()
            for value in self.json['options']['class']:
                name = value['definition']['name']
                if name in ['Archery', 'Dueling', 'Two-Weapon Fighting']:
                    fighting_styles.add(name)
            self._fighting_styles = fighting_styles
        return self._fighting_styles

    def get_prof(self, proftype):
        if not hasattr(self, 'profs'):
            p = []
            for modtype in self.json['modifiers'].values():
                for mod in modtype:
                    if mod['type'] == 'proficiency':
                        if mod['subType'] == 'simple-weapons':
                            p.extend(self.weapons.get('simple', []))
                        elif mod['subType'] == 'martial-weapons':
                            p.extend(self.weapons.get('martial', []))
                        p.append(mod['friendlySubtypeName'])
            self.profs = p
        return proftype.lower() in self.profs

    def get_relevant_atkmod(self, itemdef):
        if itemdef['attackType'] == 2:  # ranged, dex
            return self.stats['dexmod']
        elif itemdef['attackType'] == 1:  # melee
            if 'Finesse' in [p['name'] for p in itemdef['properties']]:  # finesse
                return max(self.stats['strmod'], self.stats['dexmod'])
        return self.stats['strmod']  # strength

    def get_specific_item_bonuses(self, itemId):
        out = {
            'Fixed Value Bonus': 0,
            'Fixed Value Override': None,
            'Is Hexblade': False,
            'Is Pact Weapon': False,
            # 'Is Proficient': None,
            'Name Override': None,
            'To Hit Bonus': 0,
            'To Hit Override': None,
            # 'Weapon Proficiency Level': None,
            'Dual Wield': False,
        }
        adj = self.adjustments
        for key in out:
            if key in adj and itemId in adj[key] and 'value' in adj[key][itemId]:
                out[key] = adj[key][itemId]['value'] or out[key]
        return out

    def get_attack(self, atkIn):
        return [{
            'name': atkIn['name'],
            'attackBonus': None,
            'damage': f"{atkIn['dice']['diceString']}",
            'damageType': self.damage_types.get(atkIn['damageTypeId']),
        }]

    def get_custom_attack(self, atkIn):
        name = atkIn['name']
        attackBonus = None
        damageBonus = (atkIn['fixedValue'] or 0) + (atkIn['damageBonus'] or 0)
        if atkIn['statId'] and atkIn['rangeId']:
            attackBonus = self.get_mod(atkIn['statId']) + (atkIn['toHitBonus'] or 0)
            if atkIn['isProficient']:
                attackBonus += self.stats['prof']
            damageBonus += self.get_mod(atkIn['statId'])
        elif atkIn['saveStatId'] is not None and atkIn['statId'] is not None:
            attackBonus = 8 + self.get_mod(atkIn['statId']) + self.stats['prof']
            if atkIn['fixedSaveDc']:
                attackBonus = atkIn['fixedSaveDc']
            save = self.stat_list[atkIn['saveStatId'] - 1][:3]
            attackBonus = f"DC {attackBonus} {save} save"
        diceCount = atkIn['diceCount']
        diceType = atkIn['diceType']
        damageType = self.damage_types.get(atkIn['damageTypeId'])

        damage = f"{diceCount}d{diceType}"
        if damageBonus:
            damage += f"{damageBonus:+d}"

        return [{
            'name': name,
            'attackBonus': attackBonus,
            'damage': damage,
            'damageType': damageType,
        }]

    def get_weapon_attack(self, atkIn):
        prof = self.stats['prof']
        itemdef = atkIn['definition']
        weirdBonuses = self.get_specific_item_bonuses(atkIn['id'])
        name = weirdBonuses['Name Override'] or itemdef['name']
        # get attack modifier stat
        if weirdBonuses['Is Hexblade']:
            attackMod = self.get_mod('charisma')
        else:
            attackMod = self.get_relevant_atkmod(itemdef)
        # +n magic modifier
        magicBonus = 0
        for m in itemdef['grantedModifiers']:
            if m['type'] == 'bonus' and m['subType'] == 'magic':
                magicBonus += m['value']
        # to hit bonus
        attackBonus = attackMod + magicBonus + weirdBonuses['To Hit Bonus']
        if self.get_prof(itemdef['type']) or weirdBonuses['Is Pact Weapon']:
            attackBonus += prof
        if weirdBonuses['To Hit Override']:
            attackBonus = weirdBonuses['To Hit Override']
        # damage
        diceCount = itemdef['damage']['diceCount']
        diceType = itemdef['damage']['diceValue']
        damageBonus = attackMod + magicBonus + weirdBonuses['Fixed Value Bonus']
        if weirdBonuses['Fixed Value Override']:
            damageBonus = weirdBonuses['Fixed Value Override']
        # damage type
        damageType = itemdef['damageType'].lower()
        if itemdef['magic'] or weirdBonuses['Is Pact Weapon']:
            damageType += '^'
        # fighting styles
        properties = {p['name']: p for p in itemdef['properties']}
        if 'Archery' in self.fighting_styles:
            if itemdef['attackType'] == 2:
                attackBonus += 2
        if 'Dueling' in self.fighting_styles:
            if itemdef['attackType'] == 1 and 'Two-Handed' not in properties:
                damageBonus += 2
        if 'Two-Weapon Fighting' not in self.fighting_styles:
            if weirdBonuses['Dual Wield']:
                damageBonus -= attackMod

        damage = f"{diceCount}d{diceType}"
        if damageBonus:
            damage += f"{damageBonus:+d}"

        out = [{
            'name': name,
            'attackBonus': attackBonus,
            'damage': damage,
            'damageType': damageType,
        }]

        # versatile weapons
        if 'Versatile' in properties:
            vers = properties['Versatile']['notes']
            _, _, versDie = vers.partition('d')
            if versDie:
                versDie = int(versDie)
            else:
                raise ValueError(f'Invalid Versatile die: {vers}')
            damage = f"{diceCount}d{versDie}"
            if damageBonus:
                damage += f"{damageBonus:+d}"
            out.append(
                {
                    'attackBonus': attackBonus,
                    'damage': damage,
                    'damageType': damageType,
                    'name': f"{name}2h",
                }
            )

        return out

    def get_spell_attack(self, atkIn, ability):
        for mod in atkIn['modifiers']:
            if mod['type'] == 'damage':
                break
            else:
                mod, damage, damageType = None, None, None
        if mod is not None:
            damageData = mod['die']
            damageType = mod['subType']
            if mod['atHigherLevels']:
                scaling = mod['atHigherLevels']
                if scaling['scaleType'] == 'characterlevel':
                    level = self.levels['character']
                    for scale in scaling['points']:
                        if scale['level'] <= level:
                            damageData = scale['die']
            damage = damageData['diceString']
            damageBonus = damageData['fixedValue'] or 0
            if mod['usePrimaryStat']:
                damageBonus += self.get_mod(ability)
            if damageBonus:
                damage += f"{damageBonus:+d}"
        if atkIn['requiresAttackRoll']:
            attackBonus = self.get_mod(ability) + self.stats['prof']
            attackBonus = self.get_value('spell-attacks', base=attackBonus)
        elif atkIn['requiresSavingThrow']:
            attackBonus = 8 + self.get_mod(ability) + self.stats['prof']
            attackBonus = self.get_value('spell-save-dc', base=attackBonus)
            save = self.stat_list[atkIn['saveDcAbilityId'] - 1][:3]
            attackBonus = f"DC {attackBonus} {save} save"
        else:
            attackBonus = None
        out = {
            'attackBonus': attackBonus,
            'damage': damage,
            'damageType': damageType,
            'name': atkIn['name'],
        }
        return [out]

    @property
    def attacks(self):
        """Returns a list of dicts of all of the character's attacks."""
        attacks = []
        used_names = []

        def extend(parsed_attacks):
            for atk in parsed_attacks:
                if atk['name'] in used_names:
                    num = 2
                    while f"{atk['name']}{num}" in used_names:
                        num += 1
                    atk['name'] = f"{atk['name']}{num}"
            attacks.extend(parsed_attacks)
            used_names.extend(a['name'] for a in parsed_attacks)

        for src in self.json['actions'].values():
            for action in src:
                if action['displayAsAttack']:
                    extend(self.get_attack(action))
        for action in self.json['customActions']:
            # if action['displayAsAttack'] != False:
                extend(self.get_custom_attack(action))
        for item in self.json['inventory']:
            if item['equipped'] and (item['definition']['filterType'] == "Weapon" or item.get('displayAsAttack')):
                extend(self.get_weapon_attack(item))
        # spells
        for spells in self.json['spells'].values():
            for spell in spells:
                daa = self.adjustments.get('Display As Attack', {}).get(spell['id'], {}).get('value')
                if spell['displayAsAttack'] if daa is None else daa:
                    extend(self.get_spell_attack(spell['definition'], spell['spellCastingAbilityId']))
        for spells in self.json['classSpells']:
            for spell in spells['spells']:
                daa = self.adjustments.get('Display As Attack', {}).get(spell['id'], {}).get('value')
                if spell['displayAsAttack'] if daa is None else daa:
                    stat = self.classes[spells['characterClassId']]['definition']['spellCastingAbilityId']
                    extend(self.get_spell_attack(spell['definition'], stat))
        return attacks

    # ----#-   Custom getters

    def custom_rolls(self):
        notes = self.json['notes']['otherNotes']
        notes = notes.split('\n')
        skills = {}
        for line in notes:
            m = ROLL_EXPR.match(line)
            if m is not None:
                name, expr = m.groups()
                skills[name.lower()] = expr
        return skills

    # ----#-   Embed stuff

    def color(self):
        color = (self.json.get('themeColor') or {}).get('themeColor') or '#FF0000'
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        return r * 256 * 256 + g * 256 + b

    def embed_fields(self):
        overview = (
            f"**Level:** {self.levels['character']}\n"
            f"**AC:** {self.ac}\n"
        )
        yield {'name': 'Overview', 'value': overview, 'inline': True}
        for c in self.json['classes']:
            name = c['definition']['name']
            if c['subclassDefinition'] is not None:
                name = f"{c['subclassDefinition']['name']} {name}"
            value = f"**Level:** {c['level']}"
            yield {'name': f'{name}', 'value': value, 'inline': True}
        stat_list = [s[:3] for s in self.stat_list]
        stats = ("**{}:** {} ({:+d})".format(s, self.stats[s], self.get_mod(s)) for s in stat_list)
        yield {'name': 'Stats', 'value': '\n'.join(stats), 'inline': True}
        saves = ("**{}:** {:+d}".format(s, self.skills[s + 'save']) for s in stat_list)
        yield {'name': 'Saving Throws', 'value': '\n'.join(saves), 'inline': True}

    def embed_author(self):
        return {
            'name': self.name,
            'url': self.json['readonlyUrl'],
            'icon_url': self.json['avatarUrl'],
        }


if __name__ == '__main__':
    import sys
    id = sys.argv[1]
    character = Character(id)
    print(character.name)
    # print('ac:', character.ac)
    # print(character.levels)
    # pprint(character.classes, depth=3)
    # print(character.fighting_styles)
    # pprint(character.adjustments)
    # pprint(character.stats)
    # pprint(character.skills)
    # pprint(character.attacks)
