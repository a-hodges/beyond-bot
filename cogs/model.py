#!/usr/bin/env python3

from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
)
from sqlalchemy.ext.declarative import declarative_base


class Base:
    def dict(self):
        '''
        Returns a dict of the object
        Primarily for json serialization
        '''
        return {c.key: getattr(self, c.key) for c in self.__mapper__.column_attrs}


Base = declarative_base(cls=Base)


class Config (Base):
    '''
    Stores the configuration values for the application in key value pairs
    '''
    __tablename__ = 'configuration'

    name = Column(
        String(64),
        primary_key=True,
        doc="The setting's name")
    value = Column(
        'setting', String,
        doc="The setting's value")


class Prefix (Base):
    '''
    Stores the prefixes for servers
    '''
    __tablename__ = 'prefixes'

    server = Column(
        BigInteger,
        primary_key=True,
        doc='The server id for the prefix')
    prefix = Column(
        String(64),
        doc='The prefix for the server')


class Character (Base):
    '''
    Character data
    '''
    __tablename__ = 'characters'

    server = Column(
        BigInteger,
        primary_key=True,
        doc='The server the character is on')
    user = Column(
        BigInteger,
        primary_key=True,
        doc='The id of the user of the character')
    character = Column(
        Integer,
        nullable=False,
        doc='The id of the character on D&D Beyond')

    def __str__(self):
        return f"{self.server} {self.user}"


class Blacklist (Base):
    '''
    A list of user ids that are not allowed to use the dice bot
    '''
    __tablename__ = 'blacklist'

    id = Column(
        BigInteger,
        primary_key=True,
        doc='The id of the blacklisted user')


if __name__ == '__main__':
    from operator import attrgetter

    for table in sorted(Base.metadata.tables.values(), key=attrgetter('name')):
        print(table.name)
        for column in table.columns:
            col = '{}: {}'.format(column.name, column.type)

            if column.primary_key and column.foreign_keys:
                col += ' PK & FK'
            elif column.primary_key:
                col += ' PK'
            elif column.foreign_keys:
                col += ' FK'

            if not column.nullable:
                col += ' NOT NULL'

            doc = column.doc
            print('\t{}\n\t\t{}'.format(col, doc))
        print()
