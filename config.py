"""If local_config.py exists, settings in it will overwrite these."""

import os

#: The URL to download the CSV data from
url = 'http://borisapi.herokuapp.com/stations.csv'

#: The base dir for data storage
datadir = os.path.expanduser('~/boris-bike-data')

#: The filename format for gzipped csv files downloaded from `url`. Relative to
#: `datadir`; uses `datetime.datetime.strftime` %-escapes.
filename = '%Y-%m/%Y-%m-%d/%Y-%m-%d--%H:%M:%S.csv.gz'

#: Max no. of times to attempt to download `url`.
num_request_tries = 5

try:
    from local_config import *
except ImportError:
    pass
