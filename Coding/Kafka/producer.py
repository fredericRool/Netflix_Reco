# Code inspired from Confluent Cloud official examples library
# https://github.com/confluentinc/examples/blob/7.1.1-post/clients/cloud/python/producer.py

from confluent_kafka import Producer
import json
import ccloud_lib # Library not installed with pip but imported from ccloud_lib.py
import numpy as np
import time
from datetime import datetime

import requests
import pandas as pd

# Initialize configurations from "python.config" file
CONF = ccloud_lib.read_ccloud_config("python.config")
TOPIC = "netflix_views" 

# Create Producer instance
producer_conf = ccloud_lib.pop_schema_registry_params_from_config(CONF)
producer = Producer(producer_conf)

# Create topic if it doesn't already exist
ccloud_lib.create_topic(CONF, TOPIC)

delivered_records = 0

# Callback called acked (triggered by poll() or flush())
# when a message has been successfully delivered or
# permanently failed delivery (after retries).
def acked(err, msg):
    global delivered_records
    # Delivery report handler called on successful or failed delivery of message
    if err is not None:
        print("Failed to deliver message: {}".format(err))
    else:
        delivered_records += 1
        print("Produced record to topic {} partition [{}] @ offset {}"
                .format(msg.topic(), msg.partition(), msg.offset()))

try:
    url = "https://jedha-netflix-real-time-api.herokuapp.com/users-currently-watching-movie"

    while True:

        # Data production
        data = json.loads(json.loads(requests.request("GET", url).text))
        record_key = "movies"
        record_value = json.dumps(
            {
                "data": data["data"],
                "index": data["index"],
                "columns": data["columns"]              
            }
        )
        #print("Producing record: {}\t{}".format(record_key, record_value))
        print(pd.DataFrame(data["data"], index=data["index"],columns=data["columns"]))
        # This will actually send data to your topic
        producer.produce(
            TOPIC,
            key=record_key,
            value=record_value,
            on_delivery=acked
        )
        # p.poll() serves delivery reports (on_delivery)
        # from previous produce() calls thanks to acked callback
        producer.poll(0)
        time.sleep(12) # API limited to 5 calls/minute
except KeyboardInterrupt:
    pass
finally:
    producer.flush() # Finish producing the latest event before stopping the whole script
