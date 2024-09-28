#!/usr/bin/env python3
from flask import Flask, render_template, redirect, url_for, request, make_response
import requests, json, sqlite3, math
from datetime import datetime, timedelta, date

# Constants
STATION = 'KTPA'
COLUMNS = ['temperature', 'dewpoint', 'windDirection', 'windSpeed', 'windGust', 'barometricPressure', 'seaLevelPressure', 'visibility', 'maxTemperatureLast24Hours', 'minTemperatureLast24Hours', 'precipitationLastHour', 'precipitationLast3Hours', 'precipitationLast6Hours', 'relativeHumidity', 'windChill', 'heatIndex']
DB = 'weather.db'
DAYS = 7 # If this is 7, we will get the data for the last 7 days plus today, so its actually 8 (0-7).
STYLE = 'comp'

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

# Converts relativeHumidity (%) and temperature (C) to absolute humidity (g/m^3)
# https://www.calctool.org/atmospheric-thermodynamics/absolute-humidity
def abs_humidity(RH, T):
    Pc = 22064000 # Critical pressure of water (Pa)
    Tc = 647.096 # Critical temperature of water (K)
    Rw = 0.4615 # Specific gas constant for water vapor (J/g K)
    # Rw = 461.5 # Specific gas constant for water vapor (J/kg K)

    # Empirical constants
    a1 = -7.85951783
    a2 = 1.84408259
    a3 = -11.7866497
    a4 = 22.6807411
    a5 = -15.9618719
    a6 = 1.80122502

    T = T + 273.15 # Convert C to K
    tau = 1 - (T / Tc)

    # Saturation vapor pressure (Pa)
    Ps = Pc * math.exp(Tc / T * (a1 * tau + a2 * tau ** 1.5 + a3 * tau ** 3 + a4 * tau ** 3.5 + a5 * tau ** 4 + a6 * tau ** 7.5))

    # Actual vapor pressure (Pa)
    Pa = Ps * RH / 100

    # Absolute humidity (kg/m^3)
    AH = Pa / (Rw * T)
    
    return AH

# Query the database
# Return a list of touples with the x and y data
# X is a datetime string like "YYYY-MM-DD HH:MM:SS"
#   It returns results for the past N days plus today 
#   Times are in server time, US Eastern
# Temperature is in F
# Pressure is in inHg
# Humidity is in g/m^3
def query_value(station, days):
    # Create sql statement and date
    select = 'SELECT date, time, temperature, barometricPressure, relativeHumidity FROM observations WHERE station = ? AND date >= ? ORDER BY date, time ASC'
    query_start = date.today() - timedelta(days = days) # Data is pulled for last N days.
    query_start = query_start.strftime('%Y-%m-%d') # convert date to string
    data = (station, query_start)
    
    # Query the database 
    con = sqlite3.connect(DB)
    cur = con.execute(select, data)
    
    zero = datetime.strptime(query_start, '%Y-%m-%d') # Convert the string to datetime
    tz_offset = datetime.now() - datetime.utcnow() # Since the data is stored in UTC we need the offset
    
    temperature = []
    pressure = []
    humidity = []
    
    for observ in cur:
        observ_dt = observ[0] + ' ' + observ[1] # Combine date and time from the observation
        observ_dt = datetime.strptime(observ_dt, '%Y-%m-%d %H:%M:%S') # Convert the string to datetime
        observ_dt = observ_dt + tz_offset # Convert from UTC to local time
        
        # the first few observations will be outside of the range once translated to local time.
        if observ_dt < zero:
            continue 
        
        # Convert the observation from datetime to string like "YYYY-MM-DD HH:MM:SS"
        x = observ_dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Add the temperature observation to the list
        t = observ[2]
        if t != None:
            t = t * 9/5 + 32 # Convert C to F
            t = round(t, 2)
            temperature.append((x, t))

        # Add the pressure observation to the list
        p = observ[3]
        if p != None:
            p = p * 0.00029529983071445 # Convert Pa to inHg
            p = round(p, 2)
            pressure.append((x, p))

        # Add the humidity observation to the list
        t = observ[2]
        h = observ[4]
        if t != None and h != None:
            h = abs_humidity(h, t)
            humidity.append((x, h))
        
    con.close()
    return (temperature, pressure, humidity)

# same as query_value except all values are normalized between 0 and 1
def query_comp(station, days):
    # Create sql statement and date
    select = 'SELECT date, time, temperature, barometricPressure, relativeHumidity FROM observations WHERE station = ? AND date >= ? ORDER BY date, time ASC'
    query_start = date.today() - timedelta(days = days) # Data is pulled for last N days.
    query_start = query_start.strftime('%Y-%m-%d') # convert date to string
    data = (station, query_start)
    
    # Query the database 
    con = sqlite3.connect(DB)
    cur = con.execute(select, data)
    
    zero = datetime.strptime(query_start, '%Y-%m-%d') # Convert the string to datetime
    tz_offset = datetime.now() - datetime.utcnow() # Since the data is stored in UTC we need the offset
    
    temperature = []
    pressure = []
    humidity = []
    
    for observ in cur:
        observ_dt = observ[0] + ' ' + observ[1] # Combine date and time from the observation
        observ_dt = datetime.strptime(observ_dt, '%Y-%m-%d %H:%M:%S') # Convert the string to datetime
        observ_dt = observ_dt + tz_offset # Convert from UTC to local time
        
        # the first few observations will be outside of the range once translated to local time.
        if observ_dt < zero:
            continue 
        
        # Convert the observation from datetime to string like "YYYY-MM-DD HH:MM:SS"
        x = observ_dt.strftime('%Y-%m-%d %H:%M:%S')

        # Add the temperature observation to the list
        t = observ[2]
        if t != None:
            temperature.append((x, t))

        # Add the pressure observation to the list
        p = observ[3]
        if p != None:
            pressure.append((x, p))

        # Add the humidity observation to the list
        h = observ[4]
        if h != None:
            humidity.append((x, h))
        
    con.close()

    # Normalize the temperature between 0 and 1.
    # If the temperature is between 25 and 30,
    # Subtract 25 from each observation and divide by 5.
    # Round to two decimal places.
    if temperature:
        t = [y for (x, y) in temperature]
        low = min(t)
        high = max(t)
        rng = high - low
        temperature = [(x, round((y - low) / rng, 2)) for (x, y) in temperature]

    # Normalize the pressure between 0 and 1.
    # If the pressure is between 101250 and 101520,
    # Subtract 101250 from each observation and divide by 270.
    # Round to two decimal places.
    if pressure:
        p = [y for (x, y) in pressure]
        low = min(p)
        high = max(p)
        rng = high - low
        pressure = [(x, round((y - low) / rng, 2)) for (x, y) in pressure]

    # Normalize the humidity between 0 and 1
    # If the humidity is between 60% and 90%,
    # Subtract 60 from each observation and divide by 30.
    # Round to two decimal places.
    if humidity:
        h = [y for (x, y) in humidity]
        low = min(h)
        high = max(h)
        rng = high - low
        humidity = [(x, round((y - low) / rng, 2)) for (x, y) in humidity]

    return (temperature, pressure, humidity)

app = Flask(__name__)

@app.route('/')
def index():
    
    update_database(retrieve_data(STATION))
    data = query_comp(STATION, DAYS)
    
    return render_template('index.html', data = data, days = DAYS, station = STATION)

@app.route('/dets', methods=['POST'])
def dets():
    
    if request.method == 'POST':
        style = request.form['style']
        days = int(request.form['days'])
        station = request.form['station']
    else:
        style = STYLE
        days = DAYS
        station = STATION
        
    if style == 'comp':
        data = query_comp(station, days)
    elif style == 'value':
        data = query_value(station, days)
    
    return render_template('index.html', data = data, style = style, days = days, station = station)
    