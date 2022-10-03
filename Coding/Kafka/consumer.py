# Example written based on the official 
# Confluent Kakfa Get started guide https://github.com/confluentinc/examples/blob/7.1.1-post/clients/cloud/python/consumer.py

# Run on docker
# docker run -it -v "$(pwd):/home/app" jedha/confluent-image bash

from turtle import left
import pandas as pd
from confluent_kafka import Consumer
import json
import ccloud_lib
import time
import boto3
import gspread

# Initialize configurations from "python.config" file
CONF = ccloud_lib.read_ccloud_config("python.config")
TOPIC = "netflix_views" 

# Create Consumer instance
# 'auto.offset.reset=earliest' to start reading from the beginning of the
# topic if no committed offsets exist
consumer_conf = ccloud_lib.pop_schema_registry_params_from_config(CONF)
consumer_conf['group.id'] = 'my_netflix_consumer'
consumer_conf['auto.offset.reset'] = 'earliest' # This means that you will consume latest messages that your script haven't consumed yet!
consumer = Consumer(consumer_conf)

# Subscribe to topic
consumer.subscribe([TOPIC])

# Connexion AWS
aws_session = boto3.Session(
    aws_access_key_id="",
    aws_secret_access_key="",
    region_name=""
    )

# Create a client session for presonnalize
personalize = aws_session.client('personalize')

#  Configure the SDK to Personalize:
personalize_runtime = aws_session.client('personalize-runtime')

campaign_Arn = [
    "arn:aws:personalize:eu-west-1:461868250861:campaign/personalize-demo-camp1", #Data set 1
    "arn:aws:personalize:eu-west-1:461868250861:campaign/personalize-demo-camp2", #Data set 2
    "arn:aws:personalize:eu-west-1:461868250861:campaign/personalize-demo-camp3", #Data set 3
    "arn:aws:personalize:eu-west-1:461868250861:campaign/personalize-demo-camp4" #Data set 4
]
# Build a map to convert a movie id to the movie title
movies = pd.read_csv('./movie_titles.csv', usecols=[0,2], names=["movieId","mivieTittle"])
movies['movieId'] = movies['movieId'].astype(str)
movie_map = dict(movies.values)

consumer_sleep = 2
min_score_filter = 0.05
nb_max_best_reco = 5
nb_max_low_reco = 5

# Process messages
try:
    while True:
        msg = consumer.poll(1.0) # Search for all non-consumed events. It times out after 1 second
        if msg is None:
            # No message available within timeout.
            # Initial message consumption may take up to
            # `session.timeout.ms` for the consumer group to
            # rebalance and start consuming
            print("Waiting for message or event/error in poll()")
            continue
        elif msg.error():
            print('error: {}'.format(msg.error()))
        else:
            # Check for Kafka message
            record_key = msg.key()
            record_value = msg.value()
            #print("Consuming record: {}\t{}".format(record_key, record_value))
            data = json.loads(record_value)
            df = pd.DataFrame(data["data"], index=data["index"],columns=data["columns"])
           
            # Préparation des recomandations
            user_id=df.iloc[0]["customerID"] #The same customer is on the 10 rows
            timestamp=df.iloc[0]["current_time"] #The same customer is on the 10 rows
            
            best_reco_list = [] # Listera les films avec un score élevé
            low_reco_list = [] # Listera les films avec un score faible
            
            # Cumuler les recommandations des 4 campagnes AWS
            for i in range(4):
                
                # Invocation de la reco. de chaque campagne AWS
                get_recommendations_response = personalize_runtime.get_recommendations(
                    campaignArn = campaign_Arn[i],
                    userId = str(user_id),
                )
                
                # Analyse et filtrage des films recommandés
                item_list = get_recommendations_response['itemList']
                for item in item_list:
                    movie = movie_map[item['itemId']]
                    score = item['score']
                    # Orienter le film en fonction du score
                    if score>min_score_filter:
                        best_reco_list.append([movie, score])
                    else:
                        low_reco_list.append([movie, score])
            
            # Conversion en DF pour insertion dans G-Sheets
            best_reco_df = pd.DataFrame(best_reco_list, columns = ['Movie','Score']).sort_values(by="Score", ascending=False).iloc[0:nb_max_best_reco]
            low_reco_df = pd.DataFrame(low_reco_list, columns = ['Movie','Score']).sort_values(by="Score", ascending=False).iloc[0:nb_max_low_reco]
            
            # Trace du consumer pour visu. console
            if len(best_reco_df)>0:
                print("Best recommendations found for user : ", user_id)
                print(best_reco_df)
            else: 
                print("no relevant recommendation found for user : ",user_id)
               
            # Enregistrer les données dans G-Sheets (films terminés + recommandations)
            gc = gspread.service_account(filename='credentials.json')
            sh = gc.open_by_key("") # or by sheet name: gc.open("TestList")
            best_reco_wks = sh.worksheet("best_reco")
            low_reco_wks = sh.worksheet("low_reco")
            
            # Ajout dans l'onglet 'best_reco'
            if len(best_reco_df)>0:
                best_reco_wks.append_row([
                    str(user_id),
                    str(timestamp),
                    ('- '+df['Name']).to_string(index=False),
                    ('- '+best_reco_df["Movie"]).to_string(index=False),
                    best_reco_df["Score"].to_string(index=False)
                ])

            # Ajout dans l'onglet 'low_reco'
            if len(low_reco_df)>0:
                low_reco_wks.append_row([
                    str(user_id),
                    str(timestamp),
                    ('- '+df['Name']).to_string(index=False),
                    ('- '+low_reco_df['Movie']).to_string(index=False),
                    low_reco_df['Score'].to_string(index=False)
                ])

            # Wait for next message
            time.sleep(consumer_sleep)

except KeyboardInterrupt:
    pass
finally:
    # Leave group and commit final offsets
    consumer.close()