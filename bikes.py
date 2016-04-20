from __future__ import division

import datetime
from decimal import Decimal
import gzip
import xml.etree.ElementTree as ET

def parse_tfl_timestamp(ts):
    if ts:
        return datetime.datetime.fromtimestamp(int(ts)/1000)
    else:
        return None

types = {
    'int': lambda x: int(x or 0),
    'str': lambda x: str(x or ''),
    'float': Decimal,
    'bool': lambda x: {'true': True, 'false': False}[x],
    'datetime': parse_tfl_timestamp,
}

class Station(object):
    xml_elt_map = {
        'id': ('id', 'int'),
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
        station.last_updated = updated

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

