"""If local_config.py exists, settings in it will overwrite these."""

import os

#: The URL to download the CSV data from
url = 'http://www.tfl.gov.uk/tfl/syndication/feeds/cycle-hire/livecyclehireupdates.xml'

#: The base dir for data storage
datadir = os.path.expanduser('~/boris-bike-data')

#: The filename format for gzipped csv files downloaded from `url`. Relative to
#: `datadir`; uses `datetime.datetime.strftime` %-escapes.
filename = '%Y-%m/%Y-%m-%d/%Y-%m-%d--%H:%M:%S.xml.gz'

#: Max no. of times to attempt to download `url`.
num_request_tries = 5

#: URL for the database, in a format that SqlAlchemy understands. `None` to not
#: write to a database. See:
#: http://docs.sqlalchemy.org/en/rel_1_0/core/engines.html#database-urls
db_url = None

try:
    from local_config import *
except ImportError:
    pass
