from scannerpy import start_master
import os

# TODO(wcrichto): don't hardcode 8080
start_master(port='8080', block=True, watchdog=False)
