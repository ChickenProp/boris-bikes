#! /bin/sh

time=`date -u +'%F--%T'`
date=${time%--*}
month=${date%-??}

cd /home/phil/boris-bike-data
mkdir -p $month/$date

curl -sS --retry 5 http://borisapi.herokuapp.com/stations.csv \
    > $month/$date/data-$time.csv \
    2>&1

gzip $month/$date/data-$time.csv
