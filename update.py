#!/usr/bin/env python3
import requests, json, sqlite3

# Constants
STATIONS = ['KTPA','KVDF','PHTO','KOXR']
COLUMNS = ['temperature', 'dewpoint', 'windDirection', 'windSpeed', 'windGust', 'barometricPressure', 'seaLevelPressure', 'visibility', 'maxTemperatureLast24Hours', 'minTemperatureLast24Hours', 'precipitationLastHour', 'precipitationLast3Hours', 'precipitationLast6Hours', 'relativeHumidity', 'windChill', 'heatIndex']
DB = 'weather.db'

# Returns a list of tuples (station, date, time, columns from weather.gov response).
# Raises Exception if response code isnt 200 or response type isnt FeatureCollection.
def retrieve_data(station_code):
    # Request information from weather.gov
    headers = {'User-Agent': 'marleydepew@outlook.com', 'Accept': 'application/geo+json'}
    endpoint = 'https://api.weather.gov/stations/{}/observations'.format(station_code)
    response = requests.get(endpoint, headers = headers)
    
    # Check response code and type
    if response.status_code == 200:
        response_json = response.json()
        if response_json['type'] == 'FeatureCollection':
            features = response_json['features']
        else:
            Exception(response_json)
    else:
        Exception(response.status_code)
        
    # Build the response into a list of records
    records = []
    for feature in features:
        properties = feature['properties']
        station = properties['station']
        station = station[-4:]
        timestamp = properties['timestamp']
        date = timestamp[:10]
        time = timestamp[11:19]
        description = properties['textDescription']
        
        record = (station, date, time, description)
        
        for column in COLUMNS:
            property_value = properties[column].get('value')
            record += (property_value, )
            
        cloud_layers = properties['cloudLayers']
        cloud_base = []
        cloud_amount = []
        for cloud_layer in cloud_layers:
        
            value = cloud_layer['base'].get('value') # Base may-or-may-not have a value, this will return the vaule or None.
            if value:
                value = str(value)
            else:
                value = ''
                
            cloud_base.append(value)
            cloud_amount.append(cloud_layer['amount'])
            
        cloud_base_s = ','.join(cloud_base) # Convert the lists to comma separated strings
        cloud_amount_s = ','.join(cloud_amount) # Convert the lists to comma separated strings
        record += (cloud_base_s, cloud_amount_s) # Add cloud base and cloud amount to the record
            
        records.append(record) # Add the specific feature record to the list of records
        
    return records

# Accepts a list of tuples (station, date, time, columns from weather.gov response).
# Inserts the records into the observations table.
# Exceptions because of duplicate key/existing records are ignored.
def update_database(records):
    # Create sql strings
    create = 'CREATE TABLE IF NOT EXISTS observations (station, date, time, description'
    insert = 'INSERT INTO observations VALUES (?, ?, ?, ?'
    for column in COLUMNS:
        create += ', ' + column
        insert += ', ?'
    create += ', cloudBase, cloudAmount, PRIMARY KEY(station, date, time))'
    insert += ', ?, ?)'
    
    # Create connection and observations table
    con = sqlite3.connect(DB)
    con.execute(create)
    
    # Update each record in the observations table
    for record in records:
        try:
            con.execute(insert, record)
            
        except sqlite3.IntegrityError:
            pass
                
    # Save the database updates
    con.commit()
    con.close()

try:
    for station_code in STATIONS:
        update_database(retrieve_data(station_code))
        print("Updated {} successfully.".format(station_code))

except Exception as error:
    for arg in error.args:
        print(arg)