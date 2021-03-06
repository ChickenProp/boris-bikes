from __future__ import division

import sys
import os
import time
import datetime
from decimal import Decimal
import gzip
import xml.etree.ElementTree as ET
import logging

import sqlalchemy as S
import distutils.dir_util
import requests

import config

# Currently we encode floats as strings, because in testing there were
# round-trip errors encoding them to/from the db (sqlite).

logger = logging.getLogger(__name__)

class Struct(object):
    pass

class StatSnap(object):
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

        statsnap = StatSnap()
        statsnap.snapshot_date = updated

        for child in elt:
            key, type = StatSnap.xml_elt_map[child.tag]
            fn = _statsnap_types[type]
            setattr(statsnap, key, fn(child.text))

        return statsnap

    def __repr__(self):
        inner = ', '.join('%s=%r' % (k, getattr(self, k))
                          for k in self.__dict__)
        return '%s(%s)' % (self.__class__.__name__, inner)

    @staticmethod
    def parse_tfl_timestamp(ts):
        if ts:
            return datetime.datetime.fromtimestamp(int(ts)/1000)
        else:
            return None

    @staticmethod
    def parse_xml(filename):
        if filename.endswith('.gz'):
            tree = ET.parse(gzip.open(filename))
        else:
            tree = ET.parse(filename)
        root = tree.getroot()

        updated = StatSnap.parse_tfl_timestamp(root.attrib['lastUpdate'])
        return [ StatSnap.from_xml_elt(child, updated) for child in root ]

_statsnap_types = {
    'int': lambda x: int(x or 0),
    'str': lambda x: str(x or ''),
    # 'float': Decimal, # currently floats encoded as strings
    'float': lambda x: str(x or ''),
    'bool': lambda x: {'true': True, 'false': False}[x],
    'datetime': StatSnap.parse_tfl_timestamp,
}


class BorisBikesApp(object):
    db = None
    tables = None

    def __init__(self):
        self._init_tables()

    def init_db(self, url, echo=False, require=True):
        if not url:
            if require:
                raise Exception('No database provided (check config.db_url)')
            else:
                logger.info('No database provided')
                return False

        self.db = S.create_engine(url, echo=echo)
        return True

    def fetch_bikes(self):
        num_tries = 0
        exc = Exception('Could not get bike data for unknown reason')
        while num_tries < config.num_request_tries:
            num_tries += 1
            try:
                req = requests.get(config.url)
                if req.status_code == requests.codes.ok:
                    break
                else:
                    exc = Exception('URL returned code %d' % (req.status_code,))
            except Exception as e:
                exc = e

            if num_tries >= config.num_request_tries:
                raise exc

            time.sleep(1)

        return req.text

    def save_bikes(self):
        now = datetime.datetime.utcnow()
        bikes = self.fetch_bikes()

        outpath = os.path.join(config.datadir, now.strftime(config.filename))
        outdir = os.path.dirname(outpath)
        distutils.dir_util.mkpath(outdir)

        with gzip.open(outpath, 'w') as f:
            f.write(bikes)

        logger.info('%s: saved', outpath)
        return outpath

    def import_xml(self, filename):
        return self.import_xml_multi([filename])

    def import_xml_multi(self, filenames):
        self.tables.meta.create_all(self.db)
        conn = self.db.connect()

        num_succeeded = 0
        for filename in filenames:
            try:
                statsnaps = StatSnap.parse_xml(filename)
                self.insert_statsnaps(conn, statsnaps)
                num_succeeded += 1
                logger.info('%s: imported', filename)
            except IOError as e:
                logger.warn("%s: %s: %s",
                            filename, e.__class__.__name__, e.strerror)
            except S.exc.IntegrityError as e:
                logger.warn("%s: %s: %s",
                            filename, e.__class__.__name__, e.message)
            except Exception as e:
                logger.warn("%s: %s: %s", filename, e.__class__.__name__, e)

        return num_succeeded

    def insert_statsnaps(self, conn, statsnaps):
        t_stations = self.tables.stations
        station_keys = t_stations.columns.keys()
        station_keys.remove('id')

        t_snapshots = self.tables.snapshots
        snapshot_keys = t_snapshots.columns.keys()
        snapshot_keys.remove('id')
        snapshot_keys.remove('station_id')

        def get_existing_stations():
            return { tuple(r[k] for k in station_keys): r['id']
                    for r in conn.execute(S.sql.select([t_stations])) }

        existing_stations = get_existing_stations()
        needed_stations = []

        for s in statsnaps:
            stat = tuple(getattr(s, k) for k in station_keys)
            if stat not in existing_stations:
                needed_stations.append({ k: getattr(s, k)
                                         for k in station_keys })

        if needed_stations:
            conn.execute(t_stations.insert(), needed_stations)
            existing_stations = get_existing_stations()

        snapshots = []
        for s in statsnaps:
            stat = tuple(getattr(s, k) for k in station_keys)
            snap = { k: getattr(s, k) for k in snapshot_keys }
            snap['station_id'] = existing_stations[stat]
            snapshots.append(snap)

        conn.execute(t_snapshots.insert(), snapshots)

    def update_current_snapshots(self):
        # SqlAlchemy doesn't support upserts, so to get this I'd need to
        # implement it per-database. (Though realistically, delete-then-insert
        # would probably be fine in this case.) Punting on that for now. I think
        # for postgres, I'd need something like:

        # INSERT INTO current_stations (snapshot_id, tfl_id, station_id)
        # SELECT id, tfl_id, station_id
        # FROM snapshots
        #   RIGHT JOIN
        #     (SELECT tfl_id, MAX(snapshot_date) AS snapshot_date
        #      FROM snapshots GROUP BY tfl_id) latest_dates
        #   USING (tfl_id, snapshot_date)
        # ON CONFLICT (tfl_id) DO UPDATE
        #   SET snapshot_id=VALUES(snapshot_id), station_id=VALUES(station_id)

        raise NotImplementedError()

    def _init_tables(self):
        tables = self.tables = Struct()
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
            S.Column('removal_date', S.DateTime),
        )
        tables.snapshots = S.Table('snapshots', tables.meta,
            S.Column('id', S.Integer, primary_key=True),
            S.Column('station_id', None, S.ForeignKey('stations.id')),
            S.Column('tfl_id', S.Integer),
            S.Column('snapshot_date', S.DateTime),
            S.Column('num_bikes', S.Integer),
            S.Column('num_empty', S.Integer),
            S.Column('num_docks', S.Integer),

            S.Index('tfl_date', 'tfl_id', 'snapshot_date', unique=True)
        )
        tables.current_stations = S.Table('current_stations', tables.meta,
            S.Column('tfl_id', S.Integer, primary_key=True,
                     autoincrement=False),
            S.Column('station_id', None, S.ForeignKey('stations.id')),
            S.Column('snapshot_id', None, S.ForeignKey('snapshots.id'))
        )

        return tables
