from math import ceil
from collections import OrderedDict, defaultdict
from itertools import chain
import re
from pprint import pprint

import requests

URL_BASE = "https://www.dndbeyond.com"
CHARACTER_URL = URL_BASE + "/character/{id}/json"
CONFIG_URL = URL_BASE + "/api/config/json"


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
        if hasattr(self, '_adjustments'):
            return self._adjustments

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
        if hasattr(self, '_levels'):
            return self._levels

        levels = {}

        for c in self.json['classes']:
            levels[c['definition']['name'].lower()] = c['level']

        levels['character'] = sum(levels.values())

        self._levels = levels
        return levels

    @property
    def ac(self):
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
        if hasattr(self, '_fighting_styles'):
            return self._fighting_styles

        fighting_styles = set()
        for value in self.json['options']['class']:
            name = value['definition']['name']
            if name in ['Archery', 'Dueling', 'Two-Weapon Fighting']:
                fighting_styles.add(name)

        self._fighting_styles = fighting_styles
        return fighting_styles

    # ----#-   Avrae

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
            'attackBonus': 0,
            'attackBonusOverride': 0,
            'damage': 0,
            'isPact': False
        }
        for val in self.json['characterValues']:
            if val['valueId'] != itemId:
                pass
            elif val['typeId'] == 10:  # damage bonus
                out['damage'] += val['value']
            elif val['typeId'] == 12:  # to hit bonus
                out['attackBonus'] += val['value']
            elif val['typeId'] == 13:  # to hit override
                out['attackBonusOverride'] = max(val['value'], out['attackBonusOverride'])
            elif val['typeId'] == 28:  # pact weapon
                out['isPact'] = True
        return out

    def get_attack(self, atkIn, atkType):
        """Calculates and returns a list of dicts."""
        prof = self.stats['prof']
        out = []
        if atkType == 'action':
            attackBonus = None
            damage = f"{atkIn['dice']['diceString']}"
            damageType = self.damage_types.get(atkIn['damageTypeId'])
            name = atkIn['name']
        elif atkType == 'customAction':
            attackBonus = None
            damageBonus = (atkIn['fixedValue'] or 0) + (atkIn['damageBonus'] or 0)
            if atkIn['statId'] and atkIn['rangeId']:
                attackBonus = self.get_mod(atkIn['statId']) + (atkIn['toHitBonus'] or 0)
                if atkIn['isProficient']:
                    attackBonus += prof
                damageBonus = (atkIn['fixedValue'] or 0) + self.get_mod(atkIn['statId']) + (atkIn['damageBonus'] or 0)
            diceCount = atkIn['diceCount']
            diceType = atkIn['diceType']
            damage = None
            damageType = self.damage_types.get(atkIn['damageTypeId'])
            name = atkIn['name']
        elif atkType == 'item':
            itemdef = atkIn['definition']
            weirdBonuses = self.get_specific_item_bonuses(atkIn['id'])
            magicBonus = 0
            for m in itemdef['grantedModifiers']:
                if m['type'] == 'bonus' and m['subType'] == 'magic':
                    magicBonus += m['value']
            toHitBonus = magicBonus + weirdBonuses['attackBonus']
            if self.get_prof(itemdef['type']) or weirdBonuses['isPact']:
                toHitBonus += prof
            attackBonus = weirdBonuses['attackBonusOverride'] or self.get_relevant_atkmod(itemdef) + toHitBonus
            diceCount = itemdef['damage']['diceCount']
            diceType = itemdef['damage']['diceValue']
            damageBonus = self.get_relevant_atkmod(itemdef) + magicBonus + weirdBonuses['damage']
            damage = None
            damageType = itemdef['damageType'].lower()
            if itemdef['magic'] or weirdBonuses['isPact']:
                damageType += '^'
            name = itemdef['name']

            properties = {p['name']: p for p in itemdef['properties']}
            if 'Archery' in self.fighting_styles:
                if itemdef['attackType'] == 2:
                    toHitBonus += 2
            if 'Dueling' in self.fighting_styles:
                if itemdef['attackType'] == 1 and 'Two-Handed' not in properties:
                    damageBonus += 2
            if 'Two-Weapon Fighting' not in self.fighting_styles:
                dual_wield = self.adjustments.get('Dual Wield')
                if dual_wield:
                    dual_wield = dual_wield.get(atkIn['id'])
                    if dual_wield and dual_wield.get('value'):
                        damageBonus -= self.get_relevant_atkmod(itemdef)

            if 'Versatile' in properties:
                vers = properties['Versatile']['notes']
                _, _, versDie = vers.partition('d')
                if versDie:
                    versDie = int(versDie)
                else:
                    raise ValueError(f'Invalid Versatile die: {vers}')
                out.append(
                    {
                        'attackBonus': attackBonus,
                        'damage': f"{diceCount}d{versDie}+{damageBonus}",
                        'damageType': damageType,
                        'name': f"{name}2h",
                    }
                )
        else:
            return None

        if name is None:
            return None
        if attackBonus is not None:
            attackBonus = int(attackBonus)
        if damage is None:
            damage = f"{diceCount}d{diceType}"
            if damageBonus:
                damage += f"{damageBonus:+d}"

        out.insert(0, {
            'name': name,
            'attackBonus': attackBonus,
            'damage': damage,
            'damageType': damageType,
        })

        return out

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
                    extend(self.get_attack(action, "action"))
        for action in self.json['customActions']:
            # if action['displayAsAttack'] != False:
                extend(self.get_attack(action, "customAction"))
        for item in self.json['inventory']:
            if item['equipped'] and (item['definition']['filterType'] == "Weapon" or item.get('displayAsAttack')):
                extend(self.get_attack(item, "item"))
        return attacks

    # ----#-   Custom getters

    roll_expr = re.compile(r'\s*(.+?)\s*:\s*(.+)')
    attack_expr = re.compile(r'\s*(.+?)\s*:\s*([+-]?\d+)\s*,\s*([^,]+)\s*,\s*([^,]+)')

    def custom_attacks(self):
        notes = self.json['notes']['otherNotes']
        notes = notes.split('\n')
        attacks = []
        for line in notes:
            m = self.attack_expr.match(line)
            if m is not None:
                name, attackBonus, damage, damageType = m.groups()
                attacks.append({
                    'name': name,
                    'attackBonus': int(attackBonus),
                    'damage': damage,
                    'damageType': damageType
                })
        return attacks

    def all_attacks(self):
        attacks = self.custom_attacks()
        names = set(a['name'].lower() for a in attacks)
        attacks.extend(filter(lambda a: a['name'].lower() not in names, self.attacks))
        return attacks

    def custom_rolls(self):
        notes = self.json['notes']['otherNotes']
        notes = notes.split('\n')
        skills = {}
        for line in notes:
            rm = self.roll_expr.match(line)
            am = self.attack_expr.match(line)
            if am is None and rm is not None:
                name, expr = rm.groups()
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
        for c in self.json['classes']:
            level = c['level']
            name = c['definition']['name']
            if c['subclassDefinition'] is not None:
                subclass = c['subclassDefinition']['name']
                yield {'name': f'{subclass} {name}', 'value': level, 'inline': True}
            else:
                yield {'name': f'{name}', 'value': level, 'inline': True}
        yield {'name': f'AC', 'value': self.ac, 'inline': True}

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
    # print(character.fighting_styles)
    pprint(character.adjustments)
    # print('ac:', character.ac)
    # pprint(character.stats)
    pprint(character.skills)
    # pprint(character.attacks)
