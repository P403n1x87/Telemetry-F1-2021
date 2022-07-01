#!/bin/bash

/mnt/c/Program\ Files/InfluxData/influxdb/influxd.exe &
INFLUXDB=$!

sleep 10

pipenv run python -m telemetry_f1_2021.collect

kill -9 $INFLUXDB
