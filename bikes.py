from __future__ import division

import datetime
from decimal import Decimal
import gzip
import xml.etree.ElementTree as ET

import sqlalchemy as S

# Currently we encode floats as strings, because in testing there were
# round-trip errors encoding them to/from the db (sqlite).

class Struct(object):
    pass

def parse_tfl_timestamp(ts):
    if ts:
        return datetime.datetime.fromtimestamp(int(ts)/1000)
    else:
        return None

types = {
    'int': lambda x: int(x or 0),
    'str': lambda x: str(x or ''),
    # 'float': Decimal, # currently floats encoded as strings
    'float': lambda x: str(x or ''),
    'bool': lambda x: {'true': True, 'false': False}[x],
    'datetime': parse_tfl_timestamp,
}

class Station(object):
    xml_elt_map = {
        'id': ('tfl_id', 'int'),
        'name': ('name', 'str'),
        'terminalName': ('terminal_name', 'str'),
        'lat': ('lat', 'float'),
        'long': ('long', 'float'),
        'installed': ('installed', 'bool'),
        'locked': ('locked', 'bool'),
        'installDate': ('install_date', 'datetime'),
        'removalDate': ('removal_date', 'datetime'),
        'temporary': ('temporary', 'bool'),
        'nbBikes': ('num_bikes', 'int'),
        'nbEmptyDocks': ('num_empty', 'int'),
        'nbDocks': ('num_docks', 'int'),
    }
    # CSV doesn't have terminal_name, install_date, removal_date or num_docks

    # Never change: terminal_name, install_date, removal_date, temporary
    # Rarely change: name, lat, long, installed, locked
    # Often change: num_*, last_updated

    @staticmethod
    def from_xml_elt(elt, updated):
        assert elt.tag == 'station'

        station = Station()
        station.snapshot_date = updated

        for child in elt:
            key, type = Station.xml_elt_map[child.tag]
            fn = types[type]
            setattr(station, key, fn(child.text))

        return station

    def __repr__(self):
        inner = ', '.join('%s=%r' % (k, getattr(self, k))
                          for k in self.__dict__)
        return '%s(%s)' % (self.__class__.__name__, inner)

def parse_xml(filename):
    if filename.endswith('.gz'):
        tree = ET.parse(gzip.open(filename))
    else:
        tree = ET.parse(filename)
    root = tree.getroot()

    updated = parse_tfl_timestamp(root.attrib['lastUpdate'])
    return [ Station.from_xml_elt(child, updated) for child in root ]

def tables():
    tables = Struct()
    tables.meta = S.MetaData()

    tables.stations = S.Table('stations', tables.meta,
        S.Column('id', S.Integer, primary_key=True),
        S.Column('tfl_id', S.Integer, index=True),
        S.Column('name', S.String),
        S.Column('terminal_name', S.String),
        # Currently floats encoded as strings.
        # S.Column('lat', S.Numeric),
        # S.Column('long', S.Numeric),
        S.Column('lat', S.String),
        S.Column('long', S.String),
        S.Column('installed', S.Boolean),
        S.Column('locked', S.Boolean),
        S.Column('temporary', S.Boolean),
        S.Column('install_date', S.DateTime),
        S.Column('removal_date', S.DateTime)
    )
    tables.snapshots = S.Table('snapshots', tables.meta,
        S.Column('id', S.Integer, primary_key=True),
        S.Column('station_id', None, S.ForeignKey('stations.id')),
        S.Column('tfl_id', S.Integer),
        S.Column('snapshot_date', S.DateTime),
        S.Column('num_bikes', S.Integer),
        S.Column('num_empty', S.Integer),
        S.Column('num_docks', S.Integer)
    )
    tables.current_stations = S.Table('current_stations', tables.meta,
        S.Column('tfl_id', S.Integer, primary_key=True, autoincrement=False),
        S.Column('station_id', None, S.ForeignKey('stations.id')),
        S.Column('snapshot_id', None, S.ForeignKey('snapshots.id'))
    )

    return tables

def insert_parsed_stations(conn, tables, stations):
    t_stations = tables.stations
    station_keys = t_stations.columns.keys()
    station_keys.remove('id')

    t_snapshots = tables.snapshots
    snapshot_keys = t_snapshots.columns.keys()
    snapshot_keys.remove('id')
    snapshot_keys.remove('station_id')

    def get_existing_stations():
        return { tuple(r[k] for k in station_keys): r['id']
                 for r in conn.execute(S.sql.select([t_stations])) }

    existing_stations = get_existing_stations()
    needed_stations = []

    for s in stations:
        stat = tuple(getattr(s, k) for k in station_keys)
        if stat not in existing_stations:
            needed_stations.append({ k: getattr(s, k) for k in station_keys })

    if needed_stations:
        conn.execute(t_stations.insert(), needed_stations)
        existing_stations = get_existing_stations()

    snapshots = []
    for s in stations:
        stat = tuple(getattr(s, k) for k in station_keys)
        snap = { k: getattr(s, k) for k in snapshot_keys }
        snap['station_id'] = existing_stations[stat]
        snapshots.append(snap)

    conn.execute(t_snapshots.insert(), snapshots)
