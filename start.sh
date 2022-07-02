#!/bin/bash

/mnt/c/Program\ Files/InfluxData/influxdb/influxd.exe &
INFLUXDB=$!

sleep 10

pipenv run python -m f1_telemetry.collect

kill -9 $INFLUXDB
