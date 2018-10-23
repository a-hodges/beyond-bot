from math import ceil

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
            raise ValueError('Could not find character')
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
        for skill in config['abilitySkills']:
            name = slug(skill['name'])
            self.skill_list[name] = skill['stat']

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

        skills = {}
        profs = {}
        bonuses = {}
        overrides = {}
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

        self._skills = skills
        return skills

    def spellcasting(self):
        ...

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
        stats = self.stats
        prof = stats['prof']
        out = []
        attack = {
            'attackBonus': None,
            'damage': None,
            'name': None,
            'details': None
        }
        if atkType == 'action':
            attack = {
                'attackBonus': None,
                'damage': f"{atkIn['dice']['diceString']}",
                'damageType': self.damage_types.get(atkIn['damageTypeId'], 'damage'),
                'name': atkIn['name'],
                # 'details': atkIn['snippet']
            }
        elif atkType == 'customAction':
            isProf = atkIn['isProficient']
            dmgBonus = (atkIn['fixedValue'] or 0) + (atkIn['damageBonus'] or 0)
            atkBonus = None
            if atkIn['statId']:
                atkBonus = str(
                    self.stat_from_id(atkIn['statId']) + (prof if isProf else 0) + (atkIn['toHitBonus'] or 0))
                dmgBonus = (atkIn['fixedValue'] or 0) + self.stat_from_id(atkIn['statId']) + (atkIn['damageBonus'] or 0)
            attack = {
                'attackBonus': atkBonus,
                'damage': f"{atkIn['diceCount']}d{atkIn['diceType']}+{dmgBonus}",
                'damageType': self.damage_types.get(atkIn['damageTypeId'], 'damage'),
                'name': atkIn['name'],
                # 'details': atkIn['snippet']
            }
        elif atkType == 'item':
            itemdef = atkIn['definition']
            weirdBonuses = self.get_specific_item_bonuses(atkIn['id'])
            isProf = self.get_prof(itemdef['type']) or weirdBonuses['isPact']
            magicBonus = sum(
                m['value'] for m in itemdef['grantedModifiers'] if m['type'] == 'bonus' and m['subType'] == 'magic')
            dmgBonus = self.get_relevant_atkmod(itemdef) + magicBonus + weirdBonuses['damage']
            toHitBonus = (prof if isProf else 0) + magicBonus + weirdBonuses['attackBonus']

            attack = {
                'attackBonus': str(
                    weirdBonuses['attackBonusOverride'] or self.get_relevant_atkmod(itemdef) + toHitBonus),
                'damage': f"{itemdef['damage']['diceString']}+{dmgBonus}",
                'damageType': itemdef['damageType'].lower() +
                ('^' if itemdef['magic'] or weirdBonuses['isPact'] else ''),
                'name': itemdef['name'],
                # 'details': html2text.html2text(itemdef['description'], bodywidth=0).strip()
            }

            if 'Versatile' in [p['name'] for p in itemdef['properties']]:
                versDmg = next(p['notes'] for p in itemdef['properties'] if p['name'] == 'Versatile')
                out.append(
                    {
                        'attackBonus': attack['attackBonus'],
                        'damage': f"{versDmg}+{dmgBonus}",
                        'damageType': itemdef['damageType'].lower() +
                        ('^' if itemdef['magic'] or weirdBonuses['isPact'] else ''),
                        'name': f"{itemdef['name']}2h",
                        # 'details': attack['details']
                    }
                )

        if attack['name'] is None:
            return None
        if attack['damage'] in ["", "NonedNone+0"]:
            attack['damage'] = None

        if attack['attackBonus'] is not None:
            attack['attackBonus'] = int(attack['attackBonus'])
        out.insert(0, attack)

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
                if item.get('displayAsAttack') is not False:
                    extend(self.get_attack(item, "item"))
        return attacks

    def color(self):
        color = (self.json.get('themeColor') or {}).get('themeColor') or '#FF0000'
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        return r * 256 + g * 16 + b

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
    print('ac:', character.ac)
    # print(character.stats)
    # print(character.skills)
    for attack in character.attacks:
        print(attack)
